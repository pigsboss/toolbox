#!/usr/bin/env python3
"""
PhotoRouteWeb.py - 本地 Web 服务，用于生成照片轨迹地图
"""

import os
import sys
import json
import base64
import traceback
from io import BytesIO

# 确保可以导入同目录下的 PhotoRoute 模块
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from flask import Flask, request, jsonify, render_template_string
from PIL import Image

import PhotoRoute as pr

app = Flask(__name__)

HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>PhotoRoute 地图生成器</title>
    <style>
        body { font-family: sans-serif; margin: 20px; }
        .container { max-width: 1000px; margin: auto; }
        form { display: flex; flex-wrap: wrap; gap: 10px; margin-bottom: 20px; }
        label { margin: 5px; }
        input[type=text], input[type=number], select {
            padding: 5px; width: auto;
        }
        #map-container {
            width: 100%; overflow: auto; border: 1px solid #ccc;
            display: flex; justify-content: center; align-items: center;
        }
        img { transition: transform 0.2s; transform-origin: top left; }
        #stats { margin-top: 20px; }
        #controls { display: flex; gap: 10px; margin-bottom: 10px; }
    </style>
</head>
<body>
<div class="container">
    <h1>PhotoRoute 地图生成器</h1>
    <form id="gen-form">
        <label>照片文件夹: <input type="text" name="photo_dir" value="/path/to/photos" size="50"></label>
        <label>高德 API Key: <input type="text" name="api_key" value="{{ api_key }}" size="30"></label>
        <label>投影:
            <select name="projection">
                <option value="mercator">墨卡托</option>
                <option value="gnomonic">球心切平面</option>
                <option value="mollweide">Mollweide</option>
            </select>
        </label>
        <label>分辨率(米/像素): <input type="number" name="resolution" value="50" min="1"></label>
        <label>边距(像素): <input type="number" name="margin" value="50" min="0"></label>
        <label>缩略图尺寸(像素): <input type="number" name="thumb_size" value="100" min="20"></label>
        <label>轨迹策略:
            <select name="strategy">
                <option value="auto" selected>自动</option>
                <option value="route">强制路径规划</option>
                <option value="interp">强制直接插值</option>
            </select>
        </label>
        <label>插值步长(米): <input type="number" name="step_meters" value="50" min="1"></label>
        <button type="submit">生成地图</button>
    </form>
    <div id="controls">
        <button onclick="zoomIn()">放大</button>
        <button onclick="zoomOut()">缩小</button>
        <button onclick="resetZoom()">重置</button>
        <button onclick="exportMap()">导出封面图</button>
    </div>
    <div id="map-container">
        <img id="map-img" style="max-width:100%; max-height:80vh;">
    </div>
    <div id="stats"></div>
</div>
<script>
    let currentImageData = null;
    let currentMapBase64 = null;
    let zoomFactor = 1;

    document.getElementById('gen-form').addEventListener('submit', async (e) => {
        e.preventDefault();
        const formData = new FormData(e.target);
        const response = await fetch('/generate', {
            method: 'POST',
            body: formData
        });
        const result = await response.json();
        if (result.error) {
            alert('错误: ' + result.error);
            return;
        }
        currentMapBase64 = result.map_base64;
        document.getElementById('map-img').src = 'data:image/png;base64,' + result.map_base64;
        currentImageData = result;
        updateStats(result.stats);
    });

    function updateStats(stats) {
        const statsDiv = document.getElementById('stats');
        statsDiv.innerHTML = `
            <h3>统计信息</h3>
            <ul>
                <li>照片数量: ${stats.photo_count}</li>
                <li>轨迹总里程: ${stats.total_distance_km.toFixed(2)} km</li>
                <li>时间范围: ${stats.time_start} ~ ${stats.time_end}</li>
                ${stats.alt_min !== null ? `<li>最低海拔: ${stats.alt_min.toFixed(1)} m</li>` : ''}
                ${stats.alt_max !== null ? `<li>最高海拔: ${stats.alt_max.toFixed(1)} m</li>` : ''}
            </ul>
        `;
    }

    function zoomIn() {
        zoomFactor *= 1.2;
        applyZoom();
    }
    function zoomOut() {
        zoomFactor /= 1.2;
        applyZoom();
    }
    function resetZoom() {
        zoomFactor = 1;
        applyZoom();
    }
    function applyZoom() {
        const img = document.getElementById('map-img');
        img.style.transform = `scale(${zoomFactor})`;
        img.style.transformOrigin = '0 0';
    }

    async function exportMap() {
        if (!currentMapBase64) {
            alert('请先生成地图');
            return;
        }
        const filename = prompt('输入导出文件名 (例如: cover.png)', 'route_map.png');
        if (!filename) return;
        const response = await fetch('/export', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
                map_base64: currentMapBase64,
                filename: filename
            })
        });
        const result = await response.json();
        if (result.success) {
            alert('导出成功: ' + result.path);
        } else {
            alert('导出失败: ' + (result.error || '未知错误'));
        }
    }
</script>
</body>
</html>
"""

def compute_statistics(all_points, photo_infos):
    """计算轨迹总里程、照片数量、时间范围、海拔范围"""
    photo_count = len(photo_infos)
    total_distance_km = 0.0
    for i in range(1, len(all_points)):
        lat1, lon1 = all_points[i-1]
        lat2, lon2 = all_points[i]
        total_distance_km += pr.haversine_distance(lat1, lon1, lat2, lon2) / 1000.0

    times = [p['timestamp'] for p in photo_infos if p.get('timestamp') is not None]
    time_start = time_end = None
    if times:
        time_start = pr.datetime.fromtimestamp(min(times)).strftime('%Y-%m-%d %H:%M:%S')
        time_end = pr.datetime.fromtimestamp(max(times)).strftime('%Y-%m-%d %H:%M:%S')

    alts = [p['alt'] for p in photo_infos if p.get('alt') is not None]
    alt_min = min(alts) if alts else None
    alt_max = max(alts) if alts else None

    return {
        'photo_count': photo_count,
        'total_distance_km': total_distance_km,
        'time_start': time_start,
        'time_end': time_end,
        'alt_min': alt_min,
        'alt_max': alt_max,
    }

@app.route('/')
def index():
    api_key = pr.AMAP_API_KEY or os.environ.get('AMAP_API_KEY', '')
    return render_template_string(HTML_TEMPLATE, api_key=api_key)

@app.route('/generate', methods=['POST'])
def generate():
    try:
        photo_dir = request.form.get('photo_dir', '')
        api_key = request.form.get('api_key', pr.AMAP_API_KEY)
        projection = request.form.get('projection', 'mercator')
        resolution = float(request.form.get('resolution', 50))
        margin = int(request.form.get('margin', 50))
        thumb_size = int(request.form.get('thumb_size', 100))
        strategy = request.form.get('strategy', 'auto')
        step_meters = float(request.form.get('step_meters', 50))

        if not os.path.isdir(photo_dir):
            return jsonify({'error': f'目录不存在: {photo_dir}'}), 400

        photo_files = []
        for fn in os.listdir(photo_dir):
            ext = os.path.splitext(fn)[1].lower()
            if ext in pr.SUPPORTED_EXTS:
                photo_files.append(os.path.join(photo_dir, fn))

        print(f'发现 {len(photo_files)} 张照片，正在提取信息...')

        photo_infos = []
        for fp in photo_files:
            info = pr.get_photo_info(fp)
            if info:
                photo_infos.append(info)

        if len(photo_infos) < 2:
            return jsonify({'error': '至少需要两张包含 GPS 的照片'}), 400

        photo_infos.sort(key=lambda d: d['timestamp'])

        # 获取每张照片的逆地理编码信息（供 auto 策略使用）
        geo_cache = {}
        if api_key and strategy in ('auto', 'route'):
            for idx, info in enumerate(photo_infos):
                geo_cache[idx] = pr.reverse_geocode(
                    info['lat'], info['lon'], api_key
                )

        # 生成轨迹
        all_points = []
        for i in range(len(photo_infos) - 1):
            p1 = photo_infos[i]
            p2 = photo_infos[i + 1]

            geo1 = geo_cache.get(i)
            geo2 = geo_cache.get(i + 1)

            points, _ = pr.generate_segment_points(
                p1, p2, api_key, step_meters, strategy, geo1, geo2
            )
            all_points.extend(points)

        if not all_points:
            return jsonify({'error': '轨迹生成失败'}), 400

        all_geo_points = list(all_points)
        for info in photo_infos:
            all_geo_points.append((info['lat'], info['lon']))

        if projection == 'mercator':
            zoom, minx, miny, maxx, maxy = pr.compute_zoom_and_bounds(
                all_geo_points, margin, resolution
            )
            bbox = (minx, miny, maxx, maxy)
            map_img = pr.stitch_map(all_points, photo_infos, zoom, bbox, thumb_size)
        elif projection == 'gnomonic':
            lat_center = sum(lat for lat, _ in all_geo_points) / len(all_geo_points)
            lon_center = sum(lon for _, lon in all_geo_points) / len(all_geo_points)
            map_img = pr.stitch_map_gnomonic(
                all_points, photo_infos, resolution, margin, thumb_size,
                (lat_center, lon_center)
            )
        else:  # mollweide
            lon_center = sum(lon for _, lon in all_geo_points) / len(all_geo_points)
            map_img = pr.stitch_map_mollweide(
                all_points, photo_infos, resolution, margin, thumb_size,
                lon_center
            )

        buf = BytesIO()
        map_img.save(buf, format='PNG')
        buf.seek(0)
        map_base64 = base64.b64encode(buf.read()).decode('utf-8')

        stats = compute_statistics(all_points, photo_infos)

        return jsonify({
            'map_base64': map_base64,
            'stats': stats,
        })

    except Exception as e:
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

@app.route('/export', methods=['POST'])
def export():
    try:
        data = request.get_json()
        map_base64 = data.get('map_base64')
        filename = data.get('filename', 'exported_map.png')
        if not map_base64:
            return jsonify({'success': False, 'error': '缺少 map_base64'}), 400

        if os.path.isabs(filename):
            out_path = filename
        else:
            out_path = os.path.join(os.getcwd(), filename)

        img_data = base64.b64decode(map_base64)
        with open(out_path, 'wb') as f:
            f.write(img_data)

        return jsonify({'success': True, 'path': out_path})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

if __name__ == '__main__':
    app.run(host='127.0.0.1', port=5000, debug=True)
