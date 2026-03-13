import os
from datetime import datetime
from typing import List, Optional
from pptx import Presentation
from pptx.util import Inches, Pt, Emu


class PPTXReporter:
    """用 python-pptx 原生 slide layout 制作 PowerPoint 报告，替代 HWC report 功能。

    默认模板的 slide_layouts:
        0 - Title Slide           (title + subtitle)
        1 - Title and Content     (title + body placeholder)
        2 - Section Header
        3 - Two Content
        4 - Comparison
        5 - Title Only            (title placeholder, 内容区空白)
        6 - Blank
        7 - Content with Caption
        8 - Picture with Caption  (图片 + 标题 + 描述)
    """

    # Layout 索引常量
    LAYOUT_TITLE_SLIDE = 0
    LAYOUT_TITLE_ONLY = 5
    LAYOUT_BLANK = 6
    LAYOUT_PIC_WITH_CAPTION = 8

    def __init__(self):
        self._prs: Optional[Presentation] = None
        self._slides: List[dict] = []  # 收集的幻灯片数据

    # ── 初始化 ──

    def create(self):
        """初始化一个新的 Presentation（对应原 create_report）。"""
        self._prs = Presentation()
        # 16:9 宽屏
        self._prs.slide_width = Inches(13.333)
        self._prs.slide_height = Inches(7.5)
        self._slides.clear()

    # ── 添加幻灯片数据 ──

    def add_image_slide(self, label: str, image_path: str):
        """记录一张图片幻灯片（对应原 "One Image with Caption"）。"""
        self._slides.append({
            'type': 'image_with_caption',
            'label': label,
            'image_path': image_path,
        })

    def add_image_only_slide(self, label: str, image_path: str):
        """记录一张纯图片幻灯片（对应原 "One Image only"）。"""
        self._slides.append({
            'type': 'image_only',
            'label': label,
            'image_path': image_path,
        })

    # ── 构建 & 导出 ──

    def build(self):
        """根据收集的 _slides 数据构建所有 PowerPoint 页面。"""
        if self._prs is None:
            self.create()

        # 封面页 — 使用 Layout 0 (Title Slide)
        self._add_title_slide()

        # 内容页
        for slide_data in self._slides:
            stype = slide_data['type']
            if stype == 'image_with_caption':
                self._add_image_caption_slide(slide_data['label'], slide_data['image_path'])
            elif stype == 'image_only':
                self._add_image_only_slide(slide_data['label'], slide_data['image_path'])

    def export(self, output_path: str) -> str:
        """构建并导出 PPTX 文件。返回输出路径。"""
        self.build()
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        self._prs.save(output_path)
        return output_path

    # ── 内部方法 ──

    def _add_title_slide(self):
        """封面页：使用原生 Title Slide layout (index 0)。"""
        layout = self._prs.slide_layouts[self.LAYOUT_TITLE_SLIDE]
        slide = self._prs.slides.add_slide(layout)

        # placeholder 0 = title, placeholder 1 = subtitle
        slide.placeholders[0].text = "HyperView Post-Processing Report"
        slide.placeholders[1].text = datetime.now().strftime("%Y-%m-%d  %H:%M:%S")

    def _add_image_caption_slide(self, label: str, image_path: str):
        """One Image with Caption：使用原生 Title Only layout (index 5) + 图片。"""
        layout = self._prs.slide_layouts[self.LAYOUT_TITLE_ONLY]
        slide = self._prs.slides.add_slide(layout)

        # placeholder 0 = title
        slide.placeholders[0].text = label

        # 在标题下方放置图片，保持比例居中
        if os.path.exists(image_path):
            slide_w = self._prs.slide_width
            slide_h = self._prs.slide_height
            img_area_top = Inches(1.5)
            img_area_h = slide_h - img_area_top - Inches(0.3)
            img_area_left = Inches(0.5)
            img_area_w = slide_w - Inches(1.0)
            left, top, w, h = self._fit_image(
                image_path, img_area_left, img_area_top, img_area_w, img_area_h
            )
            slide.shapes.add_picture(image_path, left, top, w, h)

    def _add_image_only_slide(self, label: str, image_path: str):
        """One Image only：使用原生 Blank layout (index 6)，图片铺满页面。"""
        layout = self._prs.slide_layouts[self.LAYOUT_BLANK]
        slide = self._prs.slides.add_slide(layout)

        if os.path.exists(image_path):
            slide_w = self._prs.slide_width
            slide_h = self._prs.slide_height
            margin = Inches(0.2)
            left, top, w, h = self._fit_image(
                image_path, margin, margin,
                slide_w - margin * 2, slide_h - margin * 2
            )
            slide.shapes.add_picture(image_path, left, top, w, h)

    @staticmethod
    def _fit_image(image_path: str, area_left, area_top, area_w, area_h):
        """计算图片在给定区域内保持比例的最大尺寸和居中位置。

        Returns (left, top, width, height) as EMU int values.
        """
        from PIL import Image
        with Image.open(image_path) as img:
            img_w_px, img_h_px = img.size

        area_w_emu = int(area_w)
        area_h_emu = int(area_h)

        scale_w = area_w_emu / img_w_px
        scale_h = area_h_emu / img_h_px
        scale = min(scale_w, scale_h)

        final_w = int(img_w_px * scale)
        final_h = int(img_h_px * scale)

        # 居中
        left = int(area_left) + (area_w_emu - final_w) // 2
        top = int(area_top) + (area_h_emu - final_h) // 2

        return left, top, final_w, final_h
