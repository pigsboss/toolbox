#!/usr/bin/env python3
"""
PhotoRoute.py - 照片轨迹地图生成器

读取指定目录中的照片，提取 EXIF 时间与 GPS，
利用高德 LBS API 生成相邻照片间的轨迹，
并将轨迹及照片缩略图绘制在地图上。

依赖：
    pip install piexif pillow requests

用法示例：
    python PhotoRoute.py /path/to/photos --output route_map.png
"""

import os
import sys
import math
import random
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

def is_near_road(lat, lon, api_key, radius_m=DEFAULT_ROAD_RADIUS):
    """利用高德逆地理 API 判断点是否靠近道路。"""
    if not api_key:
        return False

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
        if data.get('status') == '1':
            regeo = data.get('regeocode', {})
            roads = regeo.get('roads', [])
            if roads:
                distance = float(roads[0].get('distance', 9999))
                return distance <= radius_m
    except Exception:
        pass
    return False


def amap_route_between(lat1, lon1, lat2, lon2, api_key):
    """
    调用高德驾车路径规划，返回途经点列表 [(lat, lon), ...]。
    若失败返回 None（由调用者回退到插值）。
    """
    if not api_key:
        return None

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
                return points
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


def compute_zoom_and_bounds(points, size, margin, zoom_range=(3, 18)):
    """
    自动计算最合适的缩放级别，使所有点 + margin 适应 size 画布。
    返回 (zoom, minx, miny, maxx, maxy) 全局像素坐标。
    """
    if not points:
        return 3, 0, 0, 256 * (2**3), 256 * (2**3)

    max_zoom, min_zoom = zoom_range[1], zoom_range[0]
    for zoom in range(max_zoom, min_zoom - 1, -1):
        xs = []
        ys = []
        for lat, lon in points:
            x, y = latlon_to_pixel(lat, lon, zoom)
            xs.append(x)
            ys.append(y)
        minx = min(xs) - margin
        maxx = max(xs) + margin
        miny = min(ys) - margin
        maxy = max(ys) + margin
        if (maxx - minx) <= size[0] and (maxy - miny) <= size[1]:
            return zoom, minx, miny, maxx, maxy

    # 若最小缩放仍放不下，强制使用最小缩放并扩大画布计算范围
    zoom = min_zoom
    xs, ys = [], []
    for lat, lon in points:
        x, y = latlon_to_pixel(lat, lon, zoom)
        xs.append(x)
        ys.append(y)
    minx = min(xs) - margin
    maxx = max(xs) + margin
    miny = min(ys) - margin
    maxy = max(ys) + margin
    return zoom, minx, miny, maxx, maxy


def download_tile(zoom, x, y):
    """下载高德地图瓦片，返回 PIL Image；失败返回空白灰色瓦片。"""
    domain = random.choice(AMAP_TILE_DOMAINS)
    url = AMAP_TILE_URL.format(domain=domain) + \
          f'?lang=zh_cn&size=1&scale=1&style=7&x={x}&y={y}&z={zoom}'
    try:
        resp = requests.get(url, timeout=10)
        if resp.status_code == 200:
            img = Image.open(io.BytesIO(resp.content)).convert('RGB')
            return img
    except Exception:
        pass
    # 返回空白瓦片
    return Image.new('RGB', (256, 256), (240, 240, 240))


def stitch_map(points, photo_infos, size, zoom, bbox, thumb_size):
    """
    拼接瓦片、裁剪、绘制轨迹和缩略图。
    points: 全部轨迹点 [(lat, lon), ...]
    photo_infos: 照片信息列表（已过滤有 GPS 的照片）
    size: 输出图像 (width, height)
    zoom: 缩放级别
    bbox: (minx, miny, maxx, maxy) 全局像素坐标
    thumb_size: 缩略图尺寸（像素）
    """
    minx, miny, maxx, maxy = bbox
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
    crop_left = int(minx - tile_minx * 256)
    crop_top = int(miny - tile_miny * 256)
    crop_right = int(maxx - tile_minx * 256)
    crop_bottom = int(maxy - tile_miny * 256)
    map_img = canvas.crop((crop_left, crop_top, crop_right, crop_bottom))
    map_img = map_img.resize(size, Image.LANCZOS)

    draw = ImageDraw.Draw(map_img, 'RGBA')

    # 计算缩放比例（全局像素 -> 输出图像坐标）
    scale_x = size[0] / (maxx - minx)
    scale_y = size[1] / (maxy - miny)

    def to_img_coords(lat, lon):
        px, py = latlon_to_pixel(lat, lon, zoom)
        ix = (px - minx) * scale_x
        iy = (py - miny) * scale_y
        return ix, iy

    # 绘制轨迹
    if len(points) >= 2:
        line_points = [to_img_coords(lat, lon) for lat, lon in points]
        line_points_int = [(int(x), int(y)) for x, y in line_points]
        # 阴影
        draw.line(line_points_int, fill=(0, 0, 0, 80), width=8, joint='curve')
        # 主线
        draw.line(line_points_int, fill=(255, 80, 80, 220), width=4, joint='curve')

    # 粘贴照片缩略图
    for info in photo_infos:
        ix, iy = to_img_coords(info['lat'], info['lon'])
        try:
            thumb = Image.open(info['path']).convert('RGB')
            thumb.thumbnail((thumb_size, thumb_size), Image.LANCZOS)
            # 白色边框
            border_size = 3
            bordered = ImageOps.expand(thumb, border=border_size, fill='white')
            paste_position = (int(ix - bordered.width // 2), int(iy - bordered.height // 2))
            map_img.paste(bordered, paste_position)
            # 画个小圆点标记
            draw.ellipse((ix - 4, iy - 4, ix + 4, iy + 4), fill=(255, 255, 0, 200), outline='black')
        except Exception:
            # 缩略图加载失败时，仍画一个点
            draw.ellipse((ix - 5, iy - 5, ix + 5, iy + 5), fill=(255, 0, 0), outline='white')

    return map_img


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
    parser.add_argument('--size', default='1400x900', help='输出图片尺寸 WxH')
    parser.add_argument('--thumb-size', type=int, default=100, help='缩略图尺寸（像素）')
    parser.add_argument('--margin', type=int, default=50, help='地图边距（像素）')
    parser.add_argument('--step-meters', type=float, default=50.0,
                        help='直线插值采样间隔（米），默认 50')
    parser.add_argument('--strategy', choices=['auto', 'route', 'interp'], default='auto',
                        help='轨迹生成策略：auto=自动判断是否靠近道路；route=强制路径规划；interp=强制直线插值')
    args = parser.parse_args()

    # 解析输出尺寸
    try:
        w_str, h_str = args.size.split('x')
        size = (int(w_str), int(h_str))
    except Exception:
        print(f'无效的 --size 格式：{args.size}')
        sys.exit(1)

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

    # 生成轨迹
    print('正在生成相邻照片间的轨迹...')
    all_points = []
    for i in range(len(photo_infos) - 1):
        p1 = photo_infos[i]
        p2 = photo_infos[i + 1]

        # 决定是否使用高德路径规划
        use_route = False
        if args.api_key and args.strategy in ('auto', 'route'):
            if args.strategy == 'route':
                use_route = True
            else:
                near1 = is_near_road(p1['lat'], p1['lon'], args.api_key, args.road_radius)
                near2 = is_near_road(p2['lat'], p2['lon'], args.api_key, args.road_radius)
                use_route = near1 and near2

        if use_route:
            route_points = amap_route_between(p1['lat'], p1['lon'], p2['lat'], p2['lon'], args.api_key)
            if route_points:
                all_points.extend(route_points)
            else:
                print(f'路径规划失败，使用插值：{p1["path"]} -> {p2["path"]}')
                all_points.extend(direct_interpolate(p1['lat'], p1['lon'], p2['lat'], p2['lon'], args.step_meters))
        else:
            all_points.extend(direct_interpolate(p1['lat'], p1['lon'], p2['lat'], p2['lon'], args.step_meters))

    if not all_points:
        print('轨迹生成失败。')
        sys.exit(1)

    # 去重（防止连续重复点）
    dedup_points = []
    for pt in all_points:
        if not dedup_points or (abs(dedup_points[-1][0] - pt[0]) > 1e-9 or abs(dedup_points[-1][1] - pt[1]) > 1e-9):
            dedup_points.append(pt)
    all_points = dedup_points

    # 计算地图范围与缩放
    print('正在计算地图范围与缩放级别...')
    all_geo_points = list(all_points)
    for info in photo_infos:
        all_geo_points.append((info['lat'], info['lon']))
    zoom, minx, miny, maxx, maxy = compute_zoom_and_bounds(all_geo_points, size, args.margin)
    bbox = (minx, miny, maxx, maxy)

    print(f'缩放级别：{zoom}，正在下载瓦片并绘制地图...')
    map_img = stitch_map(all_points, photo_infos, size, zoom, bbox, args.thumb_size)

    map_img.save(args.output)
    print(f'地图已保存为：{args.output}')


if __name__ == '__main__':
    main()
