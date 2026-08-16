#!/usr/bin/env python3
"""
PhotoRoute.py - 照片轨迹地图生成器

读取指定目录中的照片，提取 EXIF 时间与 GPS，
利用高德 LBS API 生成相邻照片间的轨迹，
并将轨迹及照片缩略图绘制在地图上。

依赖：
    pip install piexif pillow requests

用法示例：
    python PhotoRoute.py /path/to/photos --resolution 50 --output route_map.png
    python PhotoRoute.py /path/to/photos --projection gnomonic --resolution 50 --output route_gnomonic.png
    python PhotoRoute.py /path/to/photos --projection mollweide --resolution 50 --output route_mollweide.png
"""

import os
import sys
import math
import random
import time
import argparse
import io
from datetime import datetime

import piexif
import requests
from PIL import Image, ImageDraw, ImageOps

# ----------------------------------------------------------------------
# 高德 API Key 可通过环境变量 AMAP_API_KEY 设置，
# 或在命令行使用 --api-key 参数传入。
# ----------------------------------------------------------------------
AMAP_API_KEY = os.environ.get("AMAP_API_KEY", "")

# ----------------------------------------------------------------------
# 常量
# ----------------------------------------------------------------------
SUPPORTED_EXTS = ['.jpg', '.jpeg', '.png', '.tif', '.tiff']

# 高德 API
AMAP_REQEO_URL   = 'https://restapi.amap.com/v3/geocode/regeo'
AMAP_DRIVING_URL = 'https://restapi.amap.com/v3/direction/driving'
AMAP_TILE_DOMAINS = [1, 2, 3, 4]
AMAP_TILE_URL     = 'https://webrd0{domain}.is.autonavi.com/appmaptile'

# 默认参数
DEFAULT_ROAD_RADIUS = 200      # 米
DEFAULT_MAP_SIZE    = (1400, 900)
DEFAULT_THUMB_SIZE  = 100
DEFAULT_MARGIN      = 50
EARTH_RADIUS_M      = 6371000.0

class RateLimiter:
    """限制高德 Web API 每秒最大请求数。"""

    def __init__(self, max_per_second):
        self.interval = 1.0 / max_per_second
        self.last_call = 0.0

    def wait(self):
        now = time.time()
        elapsed = now - self.last_call
        if elapsed < self.interval:
            time.sleep(self.interval - elapsed)
        self.last_call = time.time()


# 高德 Web 服务并发限制：每秒最多 3 次
AMAP_RATE_LIMITER = RateLimiter(3)

# ----------------------------------------------------------------------
# 时间与 GPS 提取
# ----------------------------------------------------------------------

def exiftag2timestamp(exiftag):
    """从 EXIF 标签中解析时间戳，返回 Unix 秒，失败返回 None。"""
    try:
        dt_str = exiftag[0x9003].decode()
        dt = datetime.strptime(dt_str, '%Y:%m:%d %H:%M:%S')
        epoch = datetime(1970, 1, 1)
        return (dt - epoch).total_seconds()
    except (KeyError, ValueError):
        return None


def gps_to_degrees(value, ref):
    """将 piexif 的 GPS 坐标转换为十进制度。"""
    try:
        deg = value[0][0] / value[0][1]
        minute = value[1][0] / value[1][1]
        second = value[2][0] / value[2][1]
    except (ZeroDivisionError, IndexError, TypeError):
        return None

    dd = deg + minute / 60.0 + second / 3600.0
    if ref in ('S', 'W'):
        dd = -dd
    return dd


def get_photo_info(filepath):
    """
    读取单张照片的 GPS 与时间信息。
    返回 dict: {path, lat, lon, alt, timestamp}
    若无法解析返回 None。
    """
    try:
        data = piexif.load(filepath)
    except Exception:
        return None

    exif = data.get('Exif', {})
    gps = data.get('GPS', {})

    # 时间戳
    ts = exiftag2timestamp(exif)
    if ts is None:
        # 尝试用 GPS 日期/时间组合
        try:
            date_str = gps[piexif.GPSIFD.GPSDateStamp].decode()
            time_tuple = gps[piexif.GPSIFD.GPSTimeStamp]
            hour = time_tuple[0][0] / time_tuple[0][1]
            minute = time_tuple[1][0] / time_tuple[1][1]
            second = time_tuple[2][0] / time_tuple[2][1]
            dt = datetime.strptime(date_str, '%Y:%m:%d') + \
                 datetime.timedelta(hours=hour, minutes=minute, seconds=second)
            epoch = datetime(1970, 1, 1)
            ts = (dt - epoch).total_seconds()
        except Exception:
            # 回退为文件修改时间
            ts = os.path.getmtime(filepath)

    # 经纬度
    lat = None
    lon = None
    alt = None
    try:
        lat = gps_to_degrees(gps[piexif.GPSIFD.GPSLatitude],
                             gps[piexif.GPSIFD.GPSLatitudeRef].decode())
        lon = gps_to_degrees(gps[piexif.GPSIFD.GPSLongitude],
                             gps[piexif.GPSIFD.GPSLongitudeRef].decode())
        # 海拔
        alt_pair = gps.get(piexif.GPSIFD.GPSAltitude)
        if alt_pair is not None and alt_pair[1] != 0:
            alt = alt_pair[0] / alt_pair[1]
            if gps.get(piexif.GPSIFD.GPSAltitudeRef) == 1:
                alt = -alt
    except Exception:
        pass

    if lat is None or lon is None:
        return None

    return {
        'path': filepath,
        'lat': lat,
        'lon': lon,
        'alt': alt,
        'timestamp': ts,
    }


# ----------------------------------------------------------------------
# 高德 API 调用
# ----------------------------------------------------------------------

def reverse_geocode(lat, lon, api_key):
    """获取逆地理编码信息，失败返回 None。"""
    if not api_key:
        return None

    AMAP_RATE_LIMITER.wait()

    params = {
        'key': api_key,
        'location': f'{lon},{lat}',
        'extensions': 'all',
        'radius': 500,
        'roadlevel': 0,
    }

    try:
        resp = requests.get(AMAP_REQEO_URL, params=params, timeout=10)
        data = resp.json()
        if data.get('status') != '1':
            return None

        regeo = data.get('regeocode', {})
        roads = regeo.get('roads', [])

        road_name = None
        road_distance = None
        if roads:
            road_name = roads[0].get('name')
            try:
                road_distance = float(roads[0].get('distance'))
            except (TypeError, ValueError):
                road_distance = None

        return {
            'formatted_address': regeo.get('formatted_address'),
            'road_name': road_name,
            'road_distance': road_distance,
        }
    except Exception:
        return None


def is_near_road(lat, lon, api_key, radius_m=DEFAULT_ROAD_RADIUS):
    """判断坐标是否靠近道路。"""
    geo = reverse_geocode(lat, lon, api_key)
    if not geo:
        return False
    return geo.get('road_distance') is not None and geo['road_distance'] <= radius_m


def amap_route_between(lat1, lon1, lat2, lon2, api_key):
    """调用高德驾车路径规划。

    成功返回字典：
        {
            'points': [(lat, lon), ...],
            'distance': 米,
            'duration': 秒,
        }
    失败返回 None。
    """
    if not api_key:
        return None

    AMAP_RATE_LIMITER.wait()

    params = {
        'key': api_key,
        'origin': f'{lon1},{lat1}',
        'destination': f'{lon2},{lat2}',
        'extensions': 'all',
        'strategy': 0,
        'show_fields': 'polyline',
    }

    try:
        resp = requests.get(AMAP_DRIVING_URL, params=params, timeout=15)
        data = resp.json()
        if data.get('status') == '1':
            path = data['route']['paths'][0]
            points = []
            for step in path['steps']:
                polyline = step.get('polyline')
                if polyline:
                    for pair in polyline.split(';'):
                        lon, lat = map(float, pair.split(','))
                        points.append((lat, lon))

            if points:
                distance = float(path.get('distance', 0.0))
                duration = float(path.get('duration', 0.0))
                return {
                    'points': points,
                    'distance': distance,
                    'duration': duration,
                }
    except Exception:
        pass

    return None


# ----------------------------------------------------------------------
# 插值
# ----------------------------------------------------------------------

def haversine_distance(lat1, lon1, lat2, lon2):
    """计算两点间大圆距离（米）。"""
    R = 6371000.0
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


def direct_interpolate(lat1, lon1, lat2, lon2, step_meters=50.0):
    """
    在经纬度空间线性插值，返回包含首尾点的列表。
    step_meters 控制采样密度。
    """
    dist = haversine_distance(lat1, lon1, lat2, lon2)
    if dist <= 0:
        return [(lat1, lon1), (lat2, lon2)]

    n = max(int(dist / step_meters), 2)  # 至少两个点
    points = []
    for i in range(n + 1):
        frac = i / n
        lat = lat1 + (lat2 - lat1) * frac
        lon = lon1 + (lon2 - lon1) * frac
        points.append((lat, lon))
    return points


# ----------------------------------------------------------------------
# 地图投影与瓦片
# ----------------------------------------------------------------------

def latlon_to_pixel(lat, lon, zoom):
    """Web 墨卡托投影：经纬度 -> 全局像素坐标。"""
    world_size = 256 * (2 ** zoom)
    x = (lon + 180.0) / 360.0 * world_size
    sin_lat = math.sin(math.radians(lat))
    y = (0.5 - math.log((1 + sin_lat) / (1 - sin_lat)) / (4 * math.pi)) * world_size
    return x, y


def latlon_to_gnomonic(lat, lon, lat0, lon0, radius=EARTH_RADIUS_M):
    """经纬度 -> 以(lat0, lon0)为切点的球心切平面米制坐标。"""
    lat = math.radians(lat)
    lon = math.radians(lon)
    lat0 = math.radians(lat0)
    lon0 = math.radians(lon0)

    cos_c = (
        math.sin(lat0) * math.sin(lat)
        + math.cos(lat0) * math.cos(lat) * math.cos(lon - lon0)
    )
    cos_c = max(-1.0, min(1.0, cos_c))

    if cos_c <= 1e-12:
        return float('inf'), float('inf')

    x = radius * math.cos(lat) * math.sin(lon - lon0) / cos_c
    y = radius * (
        math.cos(lat0) * math.sin(lat)
        - math.sin(lat0) * math.cos(lat) * math.cos(lon - lon0)
    ) / cos_c

    return x, y


def gnomonic_to_latlon(x, y, lat0, lon0, radius=EARTH_RADIUS_M):
    """球心切平面米制坐标 -> 经纬度。"""
    rho = math.sqrt(x * x + y * y)
    c = math.atan2(rho, radius)

    lat0 = math.radians(lat0)
    lon0 = math.radians(lon0)

    if rho < 1e-9:
        return math.degrees(lat0), math.degrees(lon0)

    sin_c = math.sin(c)
    cos_c = math.cos(c)

    lat = math.asin(
        math.cos(c) * math.sin(lat0)
        + y * sin_c * math.cos(lat0) / rho
    )

    lon = lon0 + math.atan2(
        x * sin_c,
        rho * math.cos(lat0) * cos_c - y * math.sin(lat0) * sin_c
    )

    return math.degrees(lat), math.degrees(lon)


def latlon_to_mollweide(lat, lon, lon0, radius=EARTH_RADIUS_M):
    """经纬度 -> Mollweide 投影坐标（单位：米）"""
    lat = math.radians(lat)
    lon = math.radians(lon)
    lon0 = math.radians(lon0)

    theta = lat
    for _ in range(10):
        theta = theta - (2 * theta + math.sin(2 * theta) - math.pi * math.sin(lat)) / \
                        (2 + 2 * math.cos(2 * theta))

    x = (2 * math.sqrt(2) / math.pi) * radius * (lon - lon0) * math.cos(theta)
    y = math.sqrt(2) * radius * math.sin(theta)
    return x, y


def mollweide_to_latlon(x, y, lon0, radius=EARTH_RADIUS_M):
    """Mollweide 投影坐标（单位：米） -> 经纬度"""
    lon0 = math.radians(lon0)

    ratio = y / (math.sqrt(2) * radius)
    ratio = max(-1.0, min(1.0, ratio))
    theta = math.asin(ratio)

    lat = math.asin((2 * theta + math.sin(2 * theta)) / math.pi)

    cos_theta = math.cos(theta)
    if abs(cos_theta) < 1e-12:
        lon = lon0
    else:
        lon = lon0 + (math.pi * x) / (2 * math.sqrt(2) * radius * cos_theta)

    return math.degrees(lat), math.degrees(lon)


def compute_zoom_for_resolution(lat_center, target_resolution):
    """根据中心纬度和目标分辨率选择最接近的高德瓦片缩放等级。"""
    equator_m_per_px = 156543.03392804097
    cos_lat = math.cos(math.radians(lat_center))

    best_zoom = 3
    best_diff = float('inf')

    for zoom in range(3, 19):
        m_per_px = equator_m_per_px * cos_lat / (2 ** zoom)
        diff = abs(m_per_px - target_resolution)
        if diff < best_diff:
            best_diff = diff
            best_zoom = zoom

    return best_zoom


def compute_zoom_and_bounds(points, margin, target_resolution):
    """根据墨卡托投影和目标分辨率选择缩放级别，返回像素范围。"""
    if not points:
        return 3, 0, 0, 256 * (2 ** 3), 256 * (2 ** 3)

    lat_center = sum(lat for lat, _ in points) / len(points)
    zoom = compute_zoom_for_resolution(lat_center, target_resolution)

    xs = []
    ys = []
    for lat, lon in points:
        x, y = latlon_to_pixel(lat, lon, zoom)
        xs.append(x)
        ys.append(y)

    minx = int(min(xs) - margin)
    maxx = int(max(xs) + margin)
    miny = int(min(ys) - margin)
    maxy = int(max(ys) + margin)

    return zoom, minx, miny, maxx, maxy


def download_tile(zoom, x, y):
    """下载高德地图瓦片，返回 PIL Image；失败返回空白灰色瓦片。"""
    domain = random.choice(AMAP_TILE_DOMAINS)
    url = AMAP_TILE_URL.format(domain=domain) + \
          f'?lang=zh_cn&size=1&scale=1&style=7&x={x}&y={y}&z={zoom}'
    try:
        resp = requests.get(url, timeout=10)
        if resp.status_code == 200:
            img = Image.open(io.BytesIO(resp.content)).convert('RGBA').convert('RGB')
            return img
    except Exception:
        pass
    # 返回空白瓦片
    return Image.new('RGB', (256, 256), (240, 240, 240))


def stitch_map(points, photo_infos, zoom, bbox, thumb_size):
    """
    拼接瓦片、裁剪、绘制轨迹和缩略图。
    points: 全部轨迹点 [(lat, lon), ...]
    photo_infos: 照片信息列表（已过滤有 GPS 的照片）
    zoom: 缩放级别
    bbox: (minx, miny, maxx, maxy) 全局像素坐标
    thumb_size: 缩略图尺寸（像素）
    """
    minx, miny, maxx, maxy = [int(v) for v in bbox]
    world_size = 256 * (2 ** zoom)

    # 裁剪范围限定在世界内
    minx = max(0, minx)
    miny = max(0, miny)
    maxx = min(world_size, maxx)
    maxy = min(world_size, maxy)

    # 计算瓦片范围
    tile_minx = int(minx // 256)
    tile_miny = int(miny // 256)
    tile_maxx = int(math.ceil(maxx / 256)) - 1
    tile_maxy = int(math.ceil(maxy / 256)) - 1

    # 拼接画布
    canvas_width = (tile_maxx - tile_minx + 1) * 256
    canvas_height = (tile_maxy - tile_miny + 1) * 256
    canvas = Image.new('RGB', (canvas_width, canvas_height), (240, 240, 240))

    for tx in range(tile_minx, tile_maxx + 1):
        for ty in range(tile_miny, tile_maxy + 1):
            tile_img = download_tile(zoom, tx, ty)
            paste_x = (tx - tile_minx) * 256
            paste_y = (ty - tile_miny) * 256
            canvas.paste(tile_img, (paste_x, paste_y))

    # 裁剪到 bbox
    crop_left = minx - tile_minx * 256
    crop_top = miny - tile_miny * 256
    crop_right = maxx - tile_minx * 256
    crop_bottom = maxy - tile_miny * 256
    map_img = canvas.crop((crop_left, crop_top, crop_right, crop_bottom))

    draw = ImageDraw.Draw(map_img, 'RGBA')

    # 输出像素与全局像素一一对应，不进行拉伸
    def to_img_coords(lat, lon):
        px, py = latlon_to_pixel(lat, lon, zoom)
        return px - minx, py - miny

    # 绘制轨迹
    if len(points) >= 2:
        line_points = [to_img_coords(lat, lon) for lat, lon in points]
        line_points_int = [(int(round(x)), int(round(y))) for x, y in line_points]
        # 阴影
        draw.line(line_points_int, fill=(0, 0, 0, 80), width=8, joint='curve')
        # 主线
        draw.line(line_points_int, fill=(255, 80, 80, 220), width=4, joint='curve')

    # 粘贴照片缩略图
    for info in photo_infos:
        ix, iy = to_img_coords(info['lat'], info['lon'])
        ix, iy = int(round(ix)), int(round(iy))
        try:
            thumb = Image.open(info['path']).convert('RGB')
            thumb.thumbnail((thumb_size, thumb_size), Image.LANCZOS)
            # 白色边框
            border_size = 3
            bordered = ImageOps.expand(thumb, border=border_size, fill='white')
            paste_position = (ix - bordered.width // 2, iy - bordered.height // 2)
            map_img.paste(bordered, paste_position)
            # 画个小圆点标记
            draw.ellipse((ix - 4, iy - 4, ix + 4, iy + 4), fill=(255, 255, 0, 200), outline='black')
        except Exception:
            # 缩略图加载失败时，仍画一个点
            draw.ellipse((ix - 5, iy - 5, ix + 5, iy + 5), fill=(255, 0, 0), outline='white')

    return map_img


def crop_to_overlay_bbox(img, line_points, thumb_boxes, padding=10):
    """根据轨迹线和缩略图叠加层生成掩码，计算内容边界框并裁剪。"""
    mask = Image.new('L', img.size, 0)
    mask_draw = ImageDraw.Draw(mask)

    if len(line_points) >= 2:
        line_points_int = [(int(round(x)), int(round(y))) for x, y in line_points]
        mask_draw.line(line_points_int, fill=255, width=8, joint='curve')

    for box in thumb_boxes:
        left, top, right, bottom = box
        mask_draw.rectangle(
            (max(0, left-2), max(0, top-2), right+2, bottom+2),
            fill=255
        )

    bbox = mask.getbbox()
    if bbox is None:
        return img

    left = max(0, bbox[0] - padding)
    top = max(0, bbox[1] - padding)
    right = min(img.width, bbox[2] + padding)
    bottom = min(img.height, bbox[3] + padding)

    return img.crop((left, top, right, bottom))


def stitch_map_gnomonic(points, photo_infos, resolution, margin, thumb_size, center):
    """使用球心切平面投影生成地图，并裁剪到内容边界。"""
    lat0, lon0 = center

    xs = []
    ys = []
    for lat, lon in points:
        try:
            x, y = latlon_to_gnomonic(lat, lon, lat0, lon0)
            xs.append(x)
            ys.append(y)
        except Exception:
            pass

    for info in photo_infos:
        try:
            x, y = latlon_to_gnomonic(info['lat'], info['lon'], lat0, lon0)
            xs.append(x)
            ys.append(y)
        except Exception:
            pass

    if not xs:
        raise RuntimeError('无法计算 gnomonic 投影范围')

    margin_m = margin * resolution
    minx = min(xs) - margin_m
    maxx = max(xs) + margin_m
    miny = min(ys) - margin_m
    maxy = max(ys) + margin_m

    width = max(1, int(math.ceil((maxx - minx) / resolution)))
    height = max(1, int(math.ceil((maxy - miny) / resolution)))

    zoom = compute_zoom_for_resolution(lat0, resolution)

    output = Image.new('RGB', (width, height), (240, 240, 240))
    draw = ImageDraw.Draw(output, 'RGBA')

    line_pixels = []

    if len(points) >= 2:
        line_px = []
        for lat, lon in points:
            try:
                x, y = latlon_to_gnomonic(lat, lon, lat0, lon0)
                px = int(round((x - minx) / resolution))
                py = int(round((maxy - y) / resolution))
                line_px.append((px, py))
                line_pixels.append((px, py))
            except Exception:
                pass
        if len(line_px) >= 2:
            draw.line(line_px, fill=(0, 0, 0, 80), width=8, joint='curve')
            draw.line(line_px, fill=(255, 80, 80, 220), width=4, joint='curve')

    # 逐像素采样墨卡托瓦片
    tile_cache = {}

    def sample_tile(lat, lon):
        if lat > 85.05112878:
            lat = 85.05112878
        elif lat < -85.05112878:
            lat = -85.05112878

        px, py = latlon_to_pixel(lat, lon, zoom)
        tx = int(math.floor(px / 256))
        ty = int(math.floor(py / 256))

        if (tx, ty) not in tile_cache:
            tile_cache[(tx, ty)] = download_tile(zoom, tx, ty).convert('RGB')

        tile = tile_cache[(tx, ty)]
        local_x = int(px - tx * 256)
        local_y = int(py - ty * 256)
        local_x = max(0, min(255, local_x))
        local_y = max(0, min(255, local_y))
        return tile.getpixel((local_x, local_y))

    for row in range(height):
        y_m = maxy - (row + 0.5) * resolution
        for col in range(width):
            x_m = minx + (col + 0.5) * resolution
            try:
                lat, lon = gnomonic_to_latlon(x_m, y_m, lat0, lon0)
                color = sample_tile(lat, lon)
                output.putpixel((col, row), color)
            except Exception:
                pass

    thumb_boxes = []

    for info in photo_infos:
        try:
            x_m, y_m = latlon_to_gnomonic(info['lat'], info['lon'], lat0, lon0)
            px = int(round((x_m - minx) / resolution))
            py = int(round((maxy - y_m) / resolution))

            thumb = Image.open(info['path']).convert('RGB')
            thumb.thumbnail((thumb_size, thumb_size), Image.LANCZOS)
            border_size = 3
            bordered = ImageOps.expand(thumb, border=border_size, fill='white')
            paste_position = (px - bordered.width // 2, py - bordered.height // 2)
            output.paste(bordered, paste_position)
            draw.ellipse((px - 4, py - 4, px + 4, py + 4),
                         fill=(255, 255, 0, 200), outline='black')

            thumb_boxes.append((
                paste_position[0],
                paste_position[1],
                paste_position[0] + bordered.width,
                paste_position[1] + bordered.height,
            ))
        except Exception:
            pass

    return crop_to_overlay_bbox(output, line_pixels, thumb_boxes, padding=10)


def stitch_map_mollweide(points, photo_infos, resolution, margin, thumb_size, lon0):
    """使用 Mollweide 投影生成地图，并裁剪到内容边界。"""
    xs = []
    ys = []
    for lat, lon in points:
        try:
            x, y = latlon_to_mollweide(lat, lon, lon0)
            xs.append(x)
            ys.append(y)
        except Exception:
            pass

    for info in photo_infos:
        try:
            x, y = latlon_to_mollweide(info['lat'], info['lon'], lon0)
            xs.append(x)
            ys.append(y)
        except Exception:
            pass

    if not xs:
        raise RuntimeError('无法计算 Mollweide 投影范围')

    margin_m = margin * resolution
    minx = min(xs) - margin_m
    maxx = max(xs) + margin_m
    miny = min(ys) - margin_m
    maxy = max(ys) + margin_m

    width = max(1, int(math.ceil((maxx - minx) / resolution)))
    height = max(1, int(math.ceil((maxy - miny) / resolution)))

    lat_center = sum(lat for lat, _ in points) / len(points) if points else 0.0
    zoom = compute_zoom_for_resolution(lat_center, resolution)

    output = Image.new('RGB', (width, height), (240, 240, 240))
    draw = ImageDraw.Draw(output, 'RGBA')

    line_pixels = []

    if len(points) >= 2:
        line_px = []
        for lat, lon in points:
            try:
                x, y = latlon_to_mollweide(lat, lon, lon0)
                px = int(round((x - minx) / resolution))
                py = int(round((maxy - y) / resolution))
                line_px.append((px, py))
                line_pixels.append((px, py))
            except Exception:
                pass
        if len(line_px) >= 2:
            draw.line(line_px, fill=(0, 0, 0, 80), width=8, joint='curve')
            draw.line(line_px, fill=(255, 80, 80, 220), width=4, joint='curve')

    tile_cache = {}

    def sample_tile(lat, lon):
        if lat > 85.05112878:
            lat = 85.05112878
        elif lat < -85.05112878:
            lat = -85.05112878

        px, py = latlon_to_pixel(lat, lon, zoom)
        tx = int(math.floor(px / 256))
        ty = int(math.floor(py / 256))

        if (tx, ty) not in tile_cache:
            tile_cache[(tx, ty)] = download_tile(zoom, tx, ty).convert('RGB')

        tile = tile_cache[(tx, ty)]
        local_x = int(px - tx * 256)
        local_y = int(py - ty * 256)
        local_x = max(0, min(255, local_x))
        local_y = max(0, min(255, local_y))
        return tile.getpixel((local_x, local_y))

    for row in range(height):
        y_m = maxy - (row + 0.5) * resolution
        for col in range(width):
            x_m = minx + (col + 0.5) * resolution
            try:
                lat, lon = mollweide_to_latlon(x_m, y_m, lon0)
                color = sample_tile(lat, lon)
                output.putpixel((col, row), color)
            except Exception:
                pass

    thumb_boxes = []

    for info in photo_infos:
        try:
            x_m, y_m = latlon_to_mollweide(info['lat'], info['lon'], lon0)
            px = int(round((x_m - minx) / resolution))
            py = int(round((maxy - y_m) / resolution))

            thumb = Image.open(info['path']).convert('RGB')
            thumb.thumbnail((thumb_size, thumb_size), Image.LANCZOS)
            border_size = 3
            bordered = ImageOps.expand(thumb, border=border_size, fill='white')
            paste_position = (px - bordered.width // 2, py - bordered.height // 2)
            output.paste(bordered, paste_position)
            draw.ellipse((px - 4, py - 4, px + 4, py + 4),
                         fill=(255, 255, 0, 200), outline='black')

            thumb_boxes.append((
                paste_position[0],
                paste_position[1],
                paste_position[0] + bordered.width,
                paste_position[1] + bordered.height,
            ))
        except Exception:
            pass

    return crop_to_overlay_bbox(output, line_pixels, thumb_boxes, padding=10)


# ----------------------------------------------------------------------
# 主流程
# ----------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description='生成照片轨迹地图')
    parser.add_argument('photo_dir', help='照片目录')
    parser.add_argument('--api-key', default=AMAP_API_KEY, help='高德 Web 服务 API Key')
    parser.add_argument('--output', default='photo_route.png', help='输出图片文件')
    parser.add_argument('--road-radius', type=float, default=200.0,
                        help='判断靠近道路的半径（米），默认 200')
    parser.add_argument('--projection', choices=['mercator', 'gnomonic', 'mollweide'],
                        default='mercator',
                        help='地图投影：mercator=墨卡托（默认），gnomonic=球心切平面，mollweide=摩尔维特等面积投影')
    parser.add_argument('--resolution', type=float, default=50.0,
                        help='每像素对应的地面距离（米），默认 50')
    parser.add_argument('--thumb-size', type=int, default=100, help='缩略图尺寸（像素）')
    parser.add_argument('--margin', type=int, default=50, help='地图边距（像素）')
    parser.add_argument('--step-meters', type=float, default=50.0,
                        help='直线插值采样间隔（米），默认 50')
    parser.add_argument('--strategy', choices=['auto', 'route', 'interp'], default='auto',
                        help='轨迹生成策略：auto=自动判断是否靠近道路；route=强制路径规划；interp=强制直线插值')
    args = parser.parse_args()

    # 收集照片
    photo_dir = args.photo_dir
    if not os.path.isdir(photo_dir):
        print(f'目录不存在：{photo_dir}')
        sys.exit(1)

    photo_files = []
    for fn in os.listdir(photo_dir):
        ext = os.path.splitext(fn)[1].lower()
        if ext in SUPPORTED_EXTS:
            photo_files.append(os.path.join(photo_dir, fn))

    if not photo_files:
        print('未找到支持的照片文件。')
        sys.exit(1)

    print(f'发现 {len(photo_files)} 张照片，正在提取信息...')
    photo_infos = []
    for fp in photo_files:
        info = get_photo_info(fp)
        if info:
            photo_infos.append(info)
        else:
            print(f'无法解析：{fp}，已跳过。')

    if len(photo_infos) < 2:
        print('至少需要两张包含 GPS 的照片。')
        sys.exit(1)

    # 按时间排序
    photo_infos.sort(key=lambda d: d['timestamp'])

    # 获取每张照片的逆地理编码信息
    geo_cache = {}
    if args.api_key:
        print('正在获取每张照片的地理位置信息...')
        for idx, info in enumerate(photo_infos, 1):
            geo = reverse_geocode(info['lat'], info['lon'], args.api_key)
            geo_cache[idx - 1] = geo

            basename = os.path.basename(info['path'])
            address = '未知地址'
            road_desc = '未匹配到道路'

            if geo:
                if geo.get('formatted_address'):
                    address = geo['formatted_address']

                if geo.get('road_name'):
                    road_name = geo['road_name']
                    if geo.get('road_distance') is not None:
                        road_desc = f'{road_name}（{geo["road_distance"]:.0f} 米）'
                    else:
                        road_desc = road_name

            print(f'  [{idx}/{len(photo_infos)}] {basename}: {address}；最近道路: {road_desc}')

    # 生成轨迹
    print('正在生成相邻照片间的轨迹...')
    all_points = []
    for i in range(len(photo_infos) - 1):
        p1 = photo_infos[i]
        p2 = photo_infos[i + 1]
        basename1 = os.path.basename(p1['path'])
        basename2 = os.path.basename(p2['path'])

        # 决定是否使用高德路径规划
        use_route = False
        if args.api_key and args.strategy in ('auto', 'route'):
            if args.strategy == 'route':
                use_route = True
            else:
                geo1 = geo_cache.get(i)
                geo2 = geo_cache.get(i + 1)

                near1 = bool(
                    geo1
                    and geo1.get('road_distance') is not None
                    and geo1['road_distance'] <= args.road_radius
                )
                near2 = bool(
                    geo2
                    and geo2.get('road_distance') is not None
                    and geo2['road_distance'] <= args.road_radius
                )
                use_route = near1 and near2

        if use_route:
            route_result = amap_route_between(
                p1['lat'], p1['lon'], p2['lat'], p2['lon'], args.api_key
            )

            if route_result:
                route_points = route_result['points']
                all_points.extend(route_points)

                distance_km = route_result['distance'] / 1000.0
                duration_min = route_result['duration'] / 60.0

                print(
                    f'  路径规划成功 [{i + 1}/{len(photo_infos) - 1}]: '
                    f'{basename1} -> {basename2} | '
                    f'{distance_km:.2f} km, {duration_min:.1f} min, '
                    f'{len(route_points)} 个轨迹点 | '
                    f'起终点均靠近道路'
                )
            else:
                print(
                    f'  路径规划失败 [{i + 1}/{len(photo_infos) - 1}]: '
                    f'{basename1} -> {basename2} | 使用直线插值'
                )
                all_points.extend(
                    direct_interpolate(
                        p1['lat'], p1['lon'], p2['lat'], p2['lon'], args.step_meters
                    )
                )
        else:
            all_points.extend(
                direct_interpolate(
                    p1['lat'], p1['lon'], p2['lat'], p2['lon'], args.step_meters
                )
            )

    if not all_points:
        print('轨迹生成失败。')
        sys.exit(1)

    # 去重（防止连续重复点）
    dedup_points = []
    for pt in all_points:
        if not dedup_points or (abs(dedup_points[-1][0] - pt[0]) > 1e-9 or abs(dedup_points[-1][1] - pt[1]) > 1e-9):
            dedup_points.append(pt)
    all_points = dedup_points

    # 计算地图范围并绘制
    print('正在计算地图范围与投影参数...')
    all_geo_points = list(all_points)
    for info in photo_infos:
        all_geo_points.append((info['lat'], info['lon']))

    if args.projection == 'mercator':
        zoom, minx, miny, maxx, maxy = compute_zoom_and_bounds(
            all_geo_points, args.margin, args.resolution
        )
        bbox = (minx, miny, maxx, maxy)

        print(f'投影：墨卡托；缩放级别：{zoom}；正在下载瓦片并绘制地图...')
        map_img = stitch_map(all_points, photo_infos, zoom, bbox, args.thumb_size)

    elif args.projection == 'gnomonic':
        lat_center = sum(lat for lat, _ in all_geo_points) / len(all_geo_points)
        lon_center = sum(lon for _, lon in all_geo_points) / len(all_geo_points)

        print(
            f'投影：球心切平面；中心：({lat_center:.6f}, {lon_center:.6f})；'
            f'分辨率：{args.resolution} m/px；正在生成地图...'
        )
        map_img = stitch_map_gnomonic(
            all_points,
            photo_infos,
            args.resolution,
            args.margin,
            args.thumb_size,
            (lat_center, lon_center),
        )

    else:  # mollweide
        lat_center = sum(lat for lat, _ in all_geo_points) / len(all_geo_points)
        lon_center = sum(lon for _, lon in all_geo_points) / len(all_geo_points)

        print(
            f'投影：Mollweide；中心经度：{lon_center:.6f}；'
            f'分辨率：{args.resolution} m/px；正在生成地图...'
        )
        map_img = stitch_map_mollweide(
            all_points,
            photo_infos,
            args.resolution,
            args.margin,
            args.thumb_size,
            lon_center,
        )

    map_img.save(args.output)
    print(f'地图已保存为：{args.output}，尺寸：{map_img.width}x{map_img.height}')


if __name__ == '__main__':
    main()
