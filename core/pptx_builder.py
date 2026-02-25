"""用 python-pptx 从截图列表生成 PPTX，替代 hwc report export 避免重复 run。"""
import os
from pptx import Presentation
from pptx.util import Inches, Pt
from pptx.enum.text import PP_ALIGN


def build_pptx(slides: list, output_path: str) -> str:
    """
    Parameters
    ----------
    slides : list of dict
        每个 dict 包含 'image_path' 和 'label'。
    output_path : str
        输出 .pptx 路径。

    Returns
    -------
    str  实际写入的文件路径。
    """
    prs = Presentation()
    prs.slide_width = Inches(13.333)
    prs.slide_height = Inches(7.5)
    blank_layout = prs.slide_layouts[6]  # blank

    for s in slides:
        img = s.get('image_path', '')
        label = s.get('label', '')
        slide = prs.slides.add_slide(blank_layout)

        if img and os.path.isfile(img):
            slide.shapes.add_picture(img, Inches(0.5), Inches(0.5),
                                     width=Inches(12.333), height=Inches(5.8))

        txBox = slide.shapes.add_textbox(Inches(0.5), Inches(6.5),
                                         Inches(12.333), Inches(0.8))
        tf = txBox.text_frame
        tf.word_wrap = True
        p = tf.paragraphs[0]
        p.text = label
        p.font.size = Pt(18)
        p.alignment = PP_ALIGN.CENTER

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    prs.save(output_path)
    return output_path
