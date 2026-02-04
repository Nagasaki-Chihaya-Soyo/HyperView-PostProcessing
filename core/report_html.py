import os
import base64
from datetime import datetime
from typing import List
from .analysis import AnalysisResult


class HTMLReporter:
    def __init__(self):
        pass

    def _image_to_base64(self, image_path: str):
        if not os.path.exists(image_path):
            return ""
        with open(image_path, 'rb') as f:
            return base64.b64encode(f.read()).decode('utf-8')

    def _get_status_style(self, passed: bool) -> tuple:
        if passed:
            return ("PASS", "#28a745", "\u2713")
        else:
            return ("FAIL", "#dc3545", "\u2718")

    def generate(self,
                 results: List[AnalysisResult],
                 images: List[str],
                 model_path: str,
                 result_path: str,
                 output_path: str,
                 title: str = "Von Mises 应力分析报告HTML版"):
        total = len(results)
        passed_count = sum(1 for r in results if r.passed)
        failed_count = total - passed_count
        status_color = "#28a745" if failed_count == 0 else "#dc3545"
        overall_status = "PASS" if failed_count == 0 else "FAIL"
        images_html = ""
        for i, img_path in enumerate(images):
            if os.path.exists(img_path):
                b64 = self._image_to_base64(img_path)
                images_html += f'''
<div class="image-item">
    <img src ="data:image/png;base64,{b64}" alt="云图 {i+1}">
    <p>云图{i+1}</p>
</div>'''

        results_html = ""
        for i, r in enumerate(results):
            status_text, status_color_row, status_icon = self._get_status_style(r.passed)
            results_html += f'''
<tr>
    <td>{i+1}</td>
    <td>{r.peak_value:.4f}</td>
    <td>{r.peak_entity_id}</td>
    <td>{r.part_no or '-'}</td>
    <td>{r.allowable:.2f if r.allowable else '-'}</td>
    <td>{r.margin:.2f if r.margin else '-'}</td>
    <td>{r.ratio:.2% if r.ratio else '-'}</td>
    <td style="color:{status_color_row};font-weight:bold;">{status_icon} {status_text}</td>
</tr>
'''

        html = f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width,initial_scale=1.0">
    <title>{title}</title>
    <style>
        *{{ margin : 0;padding :0; box-sizing:border-box;}}
        body{{
            font-family: "Microsoft YaHei", Arial, sans-serif;
            background: #f5f5f5;
            padding: 20px;
            line-height: 1.6;
        }}
        .container{{
            max-width: 1200px;
            margin:0 auto;
            background: white;
            padding: 30px;
            border-radius: 8px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
        }}
        h1 {{
            text-align: center;
            color:#333;
            margin-bottom:10px;
            font-size:24px;
        }}
        .report-time {{
            text-align:center;
            color:#666;
            margin-bottom:30px;
        }}
        .summary {{
            display:flex;
            justify-content:center;
        }}
        .summary-item {{
            text-align: center;
        }}
        .summary-item .label{{
            font-size: 18px;
            color:#333;
            border-bottom:2px solid #007bff;
            padding-bottom:10px;
            margin-bottom: 15px;
        }}
        .info-table{{
            width: 100%;
            border-collapse: collapse;
            margin-bottom:20px;
        }}
        .info-table td {{
            padding:8px 12px;
            border:1px solid #ddd;
        }}
        .info-table td:first-child{{
            width:120px;
            background: #f8f9fa;
            font-weight:bold;
        }}
        .images {{
            display:flex;
            flex-wrap:wrap;
            gap:20px;
            justify-content: center;
        }}
        .image-item{{
            text-align:center;
        }}
        .image-item img{{
            max-width: 100%;
        }}
        .image-item p {{
            margin-top: 8px;
            color: #666;
        }}
        .results-table {{
            width: 100%;
            border-collapse:collapse
        }}
        .results-table th, .results-table td {{
            padding: 10px;
            border: 1px solid #ddd;
            text-align:center;
        }}
        .results-table th{{
            background: #007bff;
            color: white;
        }}
        .results-table tr:nth-child(even) {{
            background:#f8f9fa;
        }}
        .footer {{
            text-align:center;
            color:#999;
            font-size:12px;
            margin-top:30px;
            padding-top:20px;
            border-top: 1px solid #eee;
        }}
    </style>
</head>
<body>
    <div class="container">
        <h1>{title}</h1>
        <p class="report-time"> 生成时间：{datetime.now():%Y-%m-%d %H-%M-%S}</p>

        <div class="summary">
            <div class="summary-item"> 总体结果</div>
            <div class="value" style="color:{status_color}">{overall_status}</div>
        </div>
        <div class="summary-item">
            <div class="label">失败项</div>
            <div class="value" style="color:#dc3545">{failed_count}</div>
        </div>
    </div>

    <div class="section">
        <h2 class="section-title">文件信息</h2>
        <table class="info-table">
            <tr><td>模型文件</td><td>{model_path}</td></tr>
            <tr><td>结果文件</td><td>{result_path or '-'}</td></tr>
        </table>
    </div>

    <div class ="section">
        <h2 class="section-title">云图</h2>
        <div class="images">
            {images_html if images_html else '<p style ="color:#999">无云图</p>'}
        </div>
    </div>
    <div class="section">
        <h2 class="section-title">详细结果</h2>
        <table class="results-table">
            <thead>
                <tr>
                    <th>#</th>
                    <th>峰值(MPa)</th>
                    <th>实体ID</th>
                    <th>零件号</th>
                    <th>许用值(MPa)</th>
                    <th>裕度(MPa)</th>
                    <th>比值</th>
                    <th>结果</th>
                </tr>
            </thead>
            <tbody>
                {results_html if results_html else '<tr><td colspan="8">无数据</td></tr>'}
            </tbody>
        </table>
    </div>

    <div class="footer">
        HyperView Post-Processing Tool
    </div>
    </div>
</body>
</html>'''

        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(html)
        return output_path
