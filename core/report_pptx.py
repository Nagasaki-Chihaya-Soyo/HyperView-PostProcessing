"""
纯 Python 标准库生成 PPTX 文件（无第三方依赖）。

PPTX 本质是 ZIP 包，内含 XML + 媒体文件。
本模块用 zipfile / xml.etree 手工构建符合 Office Open XML 规范的 .pptx。
"""

import os
import struct
import zipfile
import mimetypes
from datetime import datetime
from typing import List, Optional
from xml.etree.ElementTree import Element, SubElement, tostring

# ── Office Open XML 命名空间 ──
NS = {
    'a':  'http://schemas.openxmlformats.org/drawingml/2006/main',
    'r':  'http://schemas.openxmlformats.org/officeDocument/2006/relationships',
    'p':  'http://schemas.openxmlformats.org/presentationml/2006/main',
    'ct': 'http://schemas.openxmlformats.org/package/2006/content-types',
    'rel': 'http://schemas.openxmlformats.org/package/2006/relationships',
}

# EMU 转换常量 (English Metric Units, 1 inch = 914400 EMU)
EMU_PER_INCH = 914400

def _emu(inches: float) -> int:
    return int(inches * EMU_PER_INCH)

# 16:9 页面尺寸
SLIDE_W = _emu(13.333)
SLIDE_H = _emu(7.5)


def _png_dimensions(path: str) -> tuple:
    """从 PNG 文件头读取宽高（像素），不依赖 PIL。"""
    with open(path, 'rb') as f:
        header = f.read(24)
    if header[:8] == b'\x89PNG\r\n\x1a\n':
        w, h = struct.unpack('>II', header[16:24])
        return w, h
    # 非 PNG 则返回默认尺寸
    return 1920, 1080


def _fit_image(img_w_px: int, img_h_px: int,
               area_left: int, area_top: int,
               area_w: int, area_h: int):
    """计算图片在区域内保持比例居中的 (left, top, width, height) EMU。"""
    scale = min(area_w / img_w_px, area_h / img_h_px)
    w = int(img_w_px * scale)
    h = int(img_h_px * scale)
    left = area_left + (area_w - w) // 2
    top = area_top + (area_h - h) // 2
    return left, top, w, h


class PPTXReporter:
    """纯标准库实现的 PPTX 生成器。"""

    def __init__(self):
        self._slides: List[dict] = []
        self._images: List[dict] = []  # {'path': ..., 'rId': ..., 'partname': ...}

    def create(self):
        """初始化（清空之前的数据）。"""
        self._slides.clear()
        self._images.clear()

    def add_image_slide(self, label: str, image_path: str):
        """带标题的图片幻灯片（对应 "One Image with Caption"）。"""
        self._slides.append({
            'type': 'image_with_caption',
            'label': label,
            'image_path': image_path,
        })

    def add_image_only_slide(self, label: str, image_path: str):
        """纯图片幻灯片（对应 "One Image only"）。"""
        self._slides.append({
            'type': 'image_only',
            'label': label,
            'image_path': image_path,
        })

    @staticmethod
    def insert_slides_to_pptx(pptx_path: str, file_paths: List[str]) -> str:
        """向已有 PPTX 末尾插入图片幻灯片（新建空白页 + 居中适配图片）。

        读取原 PPTX，解析现有幻灯片数量、媒体、ID，
        追加新的幻灯片后重新写入同一文件。
        file_paths 按顺序插入，每个文件一页（纯图片，居中缩放适配）。
        """
        import re
        import shutil
        import tempfile
        from xml.etree.ElementTree import parse as ET_parse, register_namespace

        # 注册命名空间以避免 ns0/ns1 前缀
        for prefix, uri in NS.items():
            register_namespace(prefix, uri)

        # 读取原 PPTX 到临时目录
        tmp_dir = tempfile.mkdtemp()
        try:
            with zipfile.ZipFile(pptx_path, 'r') as zf:
                zf.extractall(tmp_dir)

            # ── 读取幻灯片尺寸 ──
            pres_path = os.path.join(tmp_dir, 'ppt', 'presentation.xml')
            pres_tree = ET_parse(pres_path)
            pres_root = pres_tree.getroot()

            slide_w, slide_h = SLIDE_W, SLIDE_H  # 默认 16:9
            sldSz = pres_root.find(_p('sldSz'))
            if sldSz is not None:
                try:
                    slide_w = int(sldSz.get('cx', SLIDE_W))
                    slide_h = int(sldSz.get('cy', SLIDE_H))
                except (ValueError, TypeError):
                    pass

            # ── 计算现有幻灯片最大编号（避免覆盖已有页面）──
            slides_dir = os.path.join(tmp_dir, 'ppt', 'slides')
            os.makedirs(slides_dir, exist_ok=True)
            existing_slides = [f for f in os.listdir(slides_dir)
                               if f.startswith('slide') and f.endswith('.xml')]
            max_slide_num = 0
            for f in existing_slides:
                m = re.match(r'slide(\d+)\.xml', f)
                if m:
                    num = int(m.group(1))
                    if num > max_slide_num:
                        max_slide_num = num
            n_existing = max_slide_num

            # ── 计算现有媒体编号 ──
            media_dir = os.path.join(tmp_dir, 'ppt', 'media')
            os.makedirs(media_dir, exist_ok=True)
            existing_media = os.listdir(media_dir)
            img_counter = len(existing_media)

            # ── 计算最大 sldId（避免 ID 冲突）──
            sldIdLst = pres_root.find(_p('sldIdLst'))
            if sldIdLst is None:
                sldIdLst = SubElement(pres_root, _p('sldIdLst'))
            max_sld_id = 256
            for sldId in sldIdLst:
                try:
                    sid = int(sldId.get('id', '0'))
                    if sid > max_sld_id:
                        max_sld_id = sid
                except (ValueError, TypeError):
                    pass

            # ── 计算最大 rId（避免关系 ID 冲突）──
            pres_rels_path = os.path.join(tmp_dir, 'ppt', '_rels',
                                          'presentation.xml.rels')
            rels_tree = ET_parse(pres_rels_path)
            rels_root = rels_tree.getroot()
            max_rId = 0
            for rel in rels_root:
                rid_str = rel.get('Id', '')
                m = re.match(r'rId(\d+)', rid_str)
                if m:
                    rid_num = int(m.group(1))
                    if rid_num > max_rId:
                        max_rId = rid_num

            # ── 为每个文件创建幻灯片 ──
            reporter = PPTXReporter()
            new_slide_entries = []  # (slide_idx, sld_id, rId_str)

            for file_path in file_paths:
                if not os.path.exists(file_path):
                    continue

                n_existing += 1
                slide_idx = n_existing
                max_sld_id += 1
                max_rId += 1
                sld_id = max_sld_id
                rId_str = f'rId{max_rId}'
                new_slide_entries.append((slide_idx, sld_id, rId_str))

                # 拷贝媒体文件
                img_counter += 1
                ext = os.path.splitext(file_path)[1].lower() or '.png'
                media_name = f'image{img_counter}{ext}'
                shutil.copy2(file_path, os.path.join(media_dir, media_name))

                # 构建纯图片幻灯片 XML（居中适配）
                root = reporter._new_slide_element()
                cSld = SubElement(root, _p('cSld'))
                spTree = SubElement(cSld, _p('spTree'))
                reporter._add_grp_sp_pr(spTree)

                img_w, img_h = _png_dimensions(file_path)
                margin = _emu(0.2)
                left, top, w, h = _fit_image(
                    img_w, img_h, margin, margin,
                    slide_w - margin * 2, slide_h - margin * 2)
                reporter._add_picture(spTree, 'rId2', left, top, w, h)

                slide_xml = tostring(root, xml_declaration=True,
                                     encoding='UTF-8').decode()

                # 写 slide XML
                slide_file = os.path.join(slides_dir, f'slide{slide_idx}.xml')
                with open(slide_file, 'w', encoding='utf-8') as f:
                    f.write(slide_xml)

                # 写 slide rels
                rels_dir = os.path.join(slides_dir, '_rels')
                os.makedirs(rels_dir, exist_ok=True)
                rels_xml = reporter._slide_rels_xml(
                    [('rId2', f'../media/{media_name}')])
                with open(os.path.join(rels_dir, f'slide{slide_idx}.xml.rels'),
                          'w', encoding='utf-8') as f:
                    f.write(rels_xml)

            if not new_slide_entries:
                return pptx_path

            # ── 更新 presentation.xml — 添加新 slide 引用 ──
            for slide_idx, sld_id, rId_str in new_slide_entries:
                SubElement(sldIdLst, _p('sldId'), {
                    'id': str(sld_id),
                    _r('id'): rId_str
                })

            pres_tree.write(pres_path, xml_declaration=True, encoding='UTF-8')

            # ── 更新 presentation.xml.rels — 添加新 slide 关系 ──
            for slide_idx, sld_id, rId_str in new_slide_entries:
                SubElement(rels_root, '{%s}Relationship' % NS['rel'], {
                    'Id': rId_str,
                    'Type': 'http://schemas.openxmlformats.org/officeDocument/2006/relationships/slide',
                    'Target': f'slides/slide{slide_idx}.xml'
                })

            rels_tree.write(pres_rels_path, xml_declaration=True, encoding='UTF-8')

            # ── 更新 [Content_Types].xml — 添加新 slide 条目 ──
            ct_path = os.path.join(tmp_dir, '[Content_Types].xml')
            ct_tree = ET_parse(ct_path)
            ct_root = ct_tree.getroot()

            # 确保有图片扩展名的 Default
            existing_exts = {e.get('Extension') for e in ct_root
                             if e.tag.endswith('Default')}
            for ext_name in ['png', 'jpg', 'jpeg', 'gif', 'bmp']:
                if ext_name not in existing_exts:
                    ct_map = {'png': 'image/png', 'jpg': 'image/jpeg',
                              'jpeg': 'image/jpeg', 'gif': 'image/gif',
                              'bmp': 'image/bmp'}
                    if ext_name in ct_map:
                        SubElement(ct_root, '{%s}Default' % NS['ct'], {
                            'Extension': ext_name,
                            'ContentType': ct_map[ext_name]
                        })

            for slide_idx, sld_id, rId_str in new_slide_entries:
                SubElement(ct_root, '{%s}Override' % NS['ct'], {
                    'PartName': f'/ppt/slides/slide{slide_idx}.xml',
                    'ContentType': 'application/vnd.openxmlformats-officedocument.presentationml.slide+xml'
                })

            ct_tree.write(ct_path, xml_declaration=True, encoding='UTF-8')

            # ── 重新打包为 PPTX ──
            with zipfile.ZipFile(pptx_path, 'w', zipfile.ZIP_DEFLATED) as zf:
                for root_dir, dirs, files in os.walk(tmp_dir):
                    for file in files:
                        full_path = os.path.join(root_dir, file)
                        arcname = os.path.relpath(full_path, tmp_dir)
                        zf.write(full_path, arcname)

            return pptx_path
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def export(self, output_path: str) -> str:
        """构建并保存 .pptx 文件。"""
        os.makedirs(os.path.dirname(output_path), exist_ok=True)

        # 收集所有内容页数据（封面 + 用户幻灯片）
        all_slides = []  # list of (xml_bytes, rels_bytes, images_for_slide)

        # 封面
        all_slides.append(self._build_title_slide())

        # 内容页
        for sd in self._slides:
            if sd['type'] == 'image_with_caption':
                all_slides.append(self._build_image_caption_slide(sd['label'], sd['image_path']))
            elif sd['type'] == 'image_only':
                all_slides.append(self._build_image_only_slide(sd['label'], sd['image_path']))

        # ── 写 ZIP ──
        with zipfile.ZipFile(output_path, 'w', zipfile.ZIP_DEFLATED) as zf:
            # [Content_Types].xml
            zf.writestr('[Content_Types].xml', self._content_types_xml(len(all_slides)))
            # _rels/.rels
            zf.writestr('_rels/.rels', self._root_rels_xml())
            # ppt/presentation.xml
            zf.writestr('ppt/presentation.xml', self._presentation_xml(len(all_slides)))
            # ppt/_rels/presentation.xml.rels
            zf.writestr('ppt/_rels/presentation.xml.rels',
                        self._presentation_rels_xml(len(all_slides)))
            # ppt/slideMasters/slideMaster1.xml + layout + theme (最小骨架)
            zf.writestr('ppt/slideMasters/slideMaster1.xml', self._slide_master_xml())
            zf.writestr('ppt/slideMasters/_rels/slideMaster1.xml.rels',
                        self._slide_master_rels_xml())
            zf.writestr('ppt/slideLayouts/slideLayout1.xml', self._slide_layout_xml())
            zf.writestr('ppt/slideLayouts/_rels/slideLayout1.xml.rels',
                        self._slide_layout_rels_xml())
            zf.writestr('ppt/theme/theme1.xml', self._theme_xml())

            # 每页幻灯片
            img_counter = 0
            for i, (slide_xml, rels_xml, images) in enumerate(all_slides, 1):
                zf.writestr(f'ppt/slides/slide{i}.xml', slide_xml)
                # 写图片并生成 rels
                img_entries = []
                for img_info in images:
                    img_counter += 1
                    ext = os.path.splitext(img_info['path'])[1].lower() or '.png'
                    part_name = f'image{img_counter}{ext}'
                    zf.write(img_info['path'], f'ppt/media/{part_name}')
                    img_entries.append((img_info['rId'], f'../media/{part_name}'))

                zf.writestr(f'ppt/slides/_rels/slide{i}.xml.rels',
                            self._slide_rels_xml(img_entries))

        return output_path

    # ── 封面页 ──

    def _build_title_slide(self):
        """返回 (slide_xml_str, rels_xml_str, images_list)。"""
        title = "HyperView Post-Processing Report"
        subtitle = datetime.now().strftime("%Y-%m-%d  %H:%M:%S")

        root = self._new_slide_element()
        cSld = SubElement(root, _p('cSld'))
        spTree = SubElement(cSld, _p('spTree'))
        self._add_grp_sp_pr(spTree)

        # 标题文本框
        self._add_textbox(spTree, title,
                          left=_emu(1.0), top=_emu(2.2),
                          width=SLIDE_W - _emu(2.0), height=_emu(1.2),
                          font_size=3600, bold=True,
                          color='1F3864', align='ctr')
        # 副标题
        self._add_textbox(spTree, subtitle,
                          left=_emu(1.0), top=_emu(3.6),
                          width=SLIDE_W - _emu(2.0), height=_emu(0.6),
                          font_size=1600, bold=False,
                          color='787878', align='ctr')

        return tostring(root, xml_declaration=True, encoding='UTF-8').decode(), '', []

    # ── 带标题的图片页 ──

    def _build_image_caption_slide(self, label: str, image_path: str):
        images = []
        root = self._new_slide_element()
        cSld = SubElement(root, _p('cSld'))
        spTree = SubElement(cSld, _p('spTree'))
        self._add_grp_sp_pr(spTree)

        # 标题
        self._add_textbox(spTree, label,
                          left=_emu(0.5), top=_emu(0.2),
                          width=SLIDE_W - _emu(1.0), height=_emu(0.8),
                          font_size=2000, bold=True,
                          color='1F3864', align='l')

        # 图片
        if image_path and os.path.exists(image_path):
            rId = 'rId2'
            img_w, img_h = _png_dimensions(image_path)
            area_left = _emu(0.5)
            area_top = _emu(1.3)
            area_w = SLIDE_W - _emu(1.0)
            area_h = SLIDE_H - _emu(1.6)
            left, top, w, h = _fit_image(img_w, img_h, area_left, area_top, area_w, area_h)
            self._add_picture(spTree, rId, left, top, w, h)
            images.append({'path': image_path, 'rId': rId})

        return tostring(root, xml_declaration=True, encoding='UTF-8').decode(), '', images

    # ── 纯图片页 ──

    def _build_image_only_slide(self, label: str, image_path: str):
        images = []
        root = self._new_slide_element()
        cSld = SubElement(root, _p('cSld'))
        spTree = SubElement(cSld, _p('spTree'))
        self._add_grp_sp_pr(spTree)

        if image_path and os.path.exists(image_path):
            rId = 'rId2'
            img_w, img_h = _png_dimensions(image_path)
            margin = _emu(0.2)
            left, top, w, h = _fit_image(img_w, img_h, margin, margin,
                                         SLIDE_W - margin * 2, SLIDE_H - margin * 2)
            self._add_picture(spTree, rId, left, top, w, h)
            images.append({'path': image_path, 'rId': rId})

        return tostring(root, xml_declaration=True, encoding='UTF-8').decode(), '', images

    # ── XML 构建辅助 ──

    @staticmethod
    def _new_slide_element() -> Element:
        return Element(_p('sld'), {
            'xmlns:a': NS['a'],
            'xmlns:r': NS['r'],
            'xmlns:p': NS['p'],
        })

    @staticmethod
    def _add_grp_sp_pr(spTree: Element):
        """添加必需的 nvGrpSpPr / grpSpPr 骨架。"""
        nvGrpSpPr = SubElement(spTree, _p('nvGrpSpPr'))
        cNvPr = SubElement(nvGrpSpPr, _p('cNvPr'), {'id': '1', 'name': ''})
        SubElement(nvGrpSpPr, _p('cNvGrpSpPr'))
        SubElement(nvGrpSpPr, _p('nvPr'))
        grpSpPr = SubElement(spTree, _p('grpSpPr'))

    @staticmethod
    def _add_textbox(spTree: Element, text: str,
                     left: int, top: int, width: int, height: int,
                     font_size: int = 1800, bold: bool = False,
                     color: str = '000000', align: str = 'l'):
        """添加文本框 shape。"""
        sp = SubElement(spTree, _p('sp'))

        # nvSpPr
        nvSpPr = SubElement(sp, _p('nvSpPr'))
        SubElement(nvSpPr, _p('cNvPr'), {'id': '0', 'name': 'TextBox'})
        cNvSpPr = SubElement(nvSpPr, _p('cNvSpPr'), {'txBox': '1'})
        SubElement(nvSpPr, _p('nvPr'))

        # spPr
        spPr = SubElement(sp, _p('spPr'))
        xfrm = SubElement(spPr, _a('xfrm'))
        SubElement(xfrm, _a('off'), {'x': str(left), 'y': str(top)})
        SubElement(xfrm, _a('ext'), {'cx': str(width), 'cy': str(height)})
        SubElement(spPr, _a('prstGeom'), {'prst': 'rect'})

        # txBody
        txBody = SubElement(sp, _p('txBody'))
        bodyPr = SubElement(txBody, _a('bodyPr'), {'wrap': 'square', 'rtlCol': '0'})
        SubElement(txBody, _a('lstStyle'))
        p_elem = SubElement(txBody, _a('p'))
        pPr = SubElement(p_elem, _a('pPr'), {'algn': align})
        r_elem = SubElement(p_elem, _a('r'))
        rPr_attrs = {'lang': 'en-US', 'sz': str(font_size), 'dirty': '0'}
        if bold:
            rPr_attrs['b'] = '1'
        rPr = SubElement(r_elem, _a('rPr'), rPr_attrs)
        solidFill = SubElement(rPr, _a('solidFill'))
        SubElement(solidFill, _a('srgbClr'), {'val': color})
        t = SubElement(r_elem, _a('t'))
        t.text = text

    @staticmethod
    def _add_picture(spTree: Element, rId: str,
                     left: int, top: int, width: int, height: int):
        """添加图片 shape。"""
        pic = SubElement(spTree, _p('pic'))

        # nvPicPr
        nvPicPr = SubElement(pic, _p('nvPicPr'))
        SubElement(nvPicPr, _p('cNvPr'), {'id': '0', 'name': 'Picture'})
        cNvPicPr = SubElement(nvPicPr, _p('cNvPicPr'))
        SubElement(cNvPicPr, _a('picLocks'), {'noChangeAspect': '1'})
        SubElement(nvPicPr, _p('nvPr'))

        # blipFill
        blipFill = SubElement(pic, _p('blipFill'))
        SubElement(blipFill, _a('blip'), {_r('embed'): rId})
        stretch = SubElement(blipFill, _a('stretch'))
        SubElement(stretch, _a('fillRect'))

        # spPr
        spPr = SubElement(pic, _p('spPr'))
        xfrm = SubElement(spPr, _a('xfrm'))
        SubElement(xfrm, _a('off'), {'x': str(left), 'y': str(top)})
        SubElement(xfrm, _a('ext'), {'cx': str(width), 'cy': str(height)})
        SubElement(spPr, _a('prstGeom'), {'prst': 'rect'})

    # ── 包结构 XML ──

    @staticmethod
    def _content_types_xml(n_slides: int) -> str:
        root = Element('{%s}Types' % NS['ct'])
        SubElement(root, '{%s}Default' % NS['ct'],
                   {'Extension': 'rels', 'ContentType': 'application/vnd.openxmlformats-package.relationships+xml'})
        SubElement(root, '{%s}Default' % NS['ct'],
                   {'Extension': 'xml', 'ContentType': 'application/xml'})
        SubElement(root, '{%s}Default' % NS['ct'],
                   {'Extension': 'png', 'ContentType': 'image/png'})
        SubElement(root, '{%s}Default' % NS['ct'],
                   {'Extension': 'jpg', 'ContentType': 'image/jpeg'})
        SubElement(root, '{%s}Default' % NS['ct'],
                   {'Extension': 'jpeg', 'ContentType': 'image/jpeg'})
        SubElement(root, '{%s}Override' % NS['ct'], {
            'PartName': '/ppt/presentation.xml',
            'ContentType': 'application/vnd.openxmlformats-officedocument.presentationml.presentation.main+xml'
        })
        for i in range(1, n_slides + 1):
            SubElement(root, '{%s}Override' % NS['ct'], {
                'PartName': f'/ppt/slides/slide{i}.xml',
                'ContentType': 'application/vnd.openxmlformats-officedocument.presentationml.slide+xml'
            })
        SubElement(root, '{%s}Override' % NS['ct'], {
            'PartName': '/ppt/slideMasters/slideMaster1.xml',
            'ContentType': 'application/vnd.openxmlformats-officedocument.presentationml.slideMaster+xml'
        })
        SubElement(root, '{%s}Override' % NS['ct'], {
            'PartName': '/ppt/slideLayouts/slideLayout1.xml',
            'ContentType': 'application/vnd.openxmlformats-officedocument.presentationml.slideLayout+xml'
        })
        SubElement(root, '{%s}Override' % NS['ct'], {
            'PartName': '/ppt/theme/theme1.xml',
            'ContentType': 'application/vnd.openxmlformats-officedocument.theme+xml'
        })
        return tostring(root, xml_declaration=True, encoding='UTF-8').decode()

    @staticmethod
    def _root_rels_xml() -> str:
        root = Element('{%s}Relationships' % NS['rel'])
        SubElement(root, '{%s}Relationship' % NS['rel'], {
            'Id': 'rId1',
            'Type': 'http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument',
            'Target': 'ppt/presentation.xml'
        })
        return tostring(root, xml_declaration=True, encoding='UTF-8').decode()

    @staticmethod
    def _presentation_xml(n_slides: int) -> str:
        root = Element(_p('presentation'), {
            'xmlns:a': NS['a'],
            'xmlns:r': NS['r'],
            'xmlns:p': NS['p'],
        })
        sldMasterIdLst = SubElement(root, _p('sldMasterIdLst'))
        SubElement(sldMasterIdLst, _p('sldMasterId'), {
            'id': '2147483648',
            _r('id'): 'rId100'
        })
        sldIdLst = SubElement(root, _p('sldIdLst'))
        for i in range(1, n_slides + 1):
            SubElement(sldIdLst, _p('sldId'), {
                'id': str(255 + i),
                _r('id'): f'rId{i}'
            })
        sldSz = SubElement(root, _p('sldSz'), {
            'cx': str(SLIDE_W), 'cy': str(SLIDE_H), 'type': 'custom'
        })
        notesSz = SubElement(root, _p('notesSz'), {
            'cx': str(SLIDE_H), 'cy': str(SLIDE_W)
        })
        return tostring(root, xml_declaration=True, encoding='UTF-8').decode()

    @staticmethod
    def _presentation_rels_xml(n_slides: int) -> str:
        root = Element('{%s}Relationships' % NS['rel'])
        for i in range(1, n_slides + 1):
            SubElement(root, '{%s}Relationship' % NS['rel'], {
                'Id': f'rId{i}',
                'Type': 'http://schemas.openxmlformats.org/officeDocument/2006/relationships/slide',
                'Target': f'slides/slide{i}.xml'
            })
        SubElement(root, '{%s}Relationship' % NS['rel'], {
            'Id': 'rId100',
            'Type': 'http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideMaster',
            'Target': 'slideMasters/slideMaster1.xml'
        })
        SubElement(root, '{%s}Relationship' % NS['rel'], {
            'Id': 'rId101',
            'Type': 'http://schemas.openxmlformats.org/officeDocument/2006/relationships/theme',
            'Target': 'theme/theme1.xml'
        })
        return tostring(root, xml_declaration=True, encoding='UTF-8').decode()

    @staticmethod
    def _slide_rels_xml(img_entries: list) -> str:
        """img_entries: [(rId, target), ...]"""
        root = Element('{%s}Relationships' % NS['rel'])
        SubElement(root, '{%s}Relationship' % NS['rel'], {
            'Id': 'rId1',
            'Type': 'http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideLayout',
            'Target': '../slideLayouts/slideLayout1.xml'
        })
        for rId, target in img_entries:
            SubElement(root, '{%s}Relationship' % NS['rel'], {
                'Id': rId,
                'Type': 'http://schemas.openxmlformats.org/officeDocument/2006/relationships/image',
                'Target': target
            })
        return tostring(root, xml_declaration=True, encoding='UTF-8').decode()

    @staticmethod
    def _slide_master_xml() -> str:
        root = Element(_p('sldMaster'), {
            'xmlns:a': NS['a'],
            'xmlns:r': NS['r'],
            'xmlns:p': NS['p'],
        })
        cSld = SubElement(root, _p('cSld'))
        bg = SubElement(cSld, _p('bg'))
        bgPr = SubElement(bg, _p('bgPr'))
        solidFill = SubElement(bgPr, _a('solidFill'))
        SubElement(solidFill, _a('srgbClr'), {'val': 'FFFFFF'})
        SubElement(bgPr, _a('effectLst'))
        spTree = SubElement(cSld, _p('spTree'))
        # nvGrpSpPr 骨架
        nvGrpSpPr = SubElement(spTree, _p('nvGrpSpPr'))
        SubElement(nvGrpSpPr, _p('cNvPr'), {'id': '1', 'name': ''})
        SubElement(nvGrpSpPr, _p('cNvGrpSpPr'))
        SubElement(nvGrpSpPr, _p('nvPr'))
        SubElement(spTree, _p('grpSpPr'))

        clrMap = SubElement(root, _p('clrMap'), {
            'bg1': 'lt1', 'tx1': 'dk1', 'bg2': 'lt2', 'tx2': 'dk2',
            'accent1': 'accent1', 'accent2': 'accent2', 'accent3': 'accent3',
            'accent4': 'accent4', 'accent5': 'accent5', 'accent6': 'accent6',
            'hlink': 'hlink', 'folHlink': 'folHlink',
        })
        sldLayoutIdLst = SubElement(root, _p('sldLayoutIdLst'))
        SubElement(sldLayoutIdLst, _p('sldLayoutId'), {
            'id': '2147483649',
            _r('id'): 'rId1'
        })
        return tostring(root, xml_declaration=True, encoding='UTF-8').decode()

    @staticmethod
    def _slide_master_rels_xml() -> str:
        root = Element('{%s}Relationships' % NS['rel'])
        SubElement(root, '{%s}Relationship' % NS['rel'], {
            'Id': 'rId1',
            'Type': 'http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideLayout',
            'Target': '../slideLayouts/slideLayout1.xml'
        })
        SubElement(root, '{%s}Relationship' % NS['rel'], {
            'Id': 'rId2',
            'Type': 'http://schemas.openxmlformats.org/officeDocument/2006/relationships/theme',
            'Target': '../theme/theme1.xml'
        })
        return tostring(root, xml_declaration=True, encoding='UTF-8').decode()

    @staticmethod
    def _slide_layout_xml() -> str:
        root = Element(_p('sldLayout'), {
            'xmlns:a': NS['a'],
            'xmlns:r': NS['r'],
            'xmlns:p': NS['p'],
            'type': 'blank',
        })
        cSld = SubElement(root, _p('cSld'))
        spTree = SubElement(cSld, _p('spTree'))
        nvGrpSpPr = SubElement(spTree, _p('nvGrpSpPr'))
        SubElement(nvGrpSpPr, _p('cNvPr'), {'id': '1', 'name': ''})
        SubElement(nvGrpSpPr, _p('cNvGrpSpPr'))
        SubElement(nvGrpSpPr, _p('nvPr'))
        SubElement(spTree, _p('grpSpPr'))
        return tostring(root, xml_declaration=True, encoding='UTF-8').decode()

    @staticmethod
    def _slide_layout_rels_xml() -> str:
        root = Element('{%s}Relationships' % NS['rel'])
        SubElement(root, '{%s}Relationship' % NS['rel'], {
            'Id': 'rId1',
            'Type': 'http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideMaster',
            'Target': '../slideMasters/slideMaster1.xml'
        })
        return tostring(root, xml_declaration=True, encoding='UTF-8').decode()

    @staticmethod
    def _theme_xml() -> str:
        """最小化的 Office 主题 XML。"""
        root = Element(_a('theme'), {
            'xmlns:a': NS['a'],
            'name': 'HyperView Theme',
        })
        themeElements = SubElement(root, _a('themeElements'))

        # clrScheme
        clrScheme = SubElement(themeElements, _a('clrScheme'), {'name': 'Custom'})
        for name, val in [
            ('dk1', '000000'), ('lt1', 'FFFFFF'), ('dk2', '1F3864'), ('lt2', 'E7E6E6'),
            ('accent1', '4472C4'), ('accent2', 'ED7D31'), ('accent3', 'A5A5A5'),
            ('accent4', 'FFC000'), ('accent5', '5B9BD5'), ('accent6', '70AD47'),
            ('hlink', '0563C1'), ('folHlink', '954F72'),
        ]:
            elem = SubElement(clrScheme, _a(name))
            SubElement(elem, _a('srgbClr'), {'val': val})

        # fontScheme
        fontScheme = SubElement(themeElements, _a('fontScheme'), {'name': 'Custom'})
        majorFont = SubElement(fontScheme, _a('majorFont'))
        SubElement(majorFont, _a('latin'), {'typeface': 'Calibri'})
        SubElement(majorFont, _a('ea'), {'typeface': ''})
        SubElement(majorFont, _a('cs'), {'typeface': ''})
        minorFont = SubElement(fontScheme, _a('minorFont'))
        SubElement(minorFont, _a('latin'), {'typeface': 'Calibri'})
        SubElement(minorFont, _a('ea'), {'typeface': ''})
        SubElement(minorFont, _a('cs'), {'typeface': ''})

        # fmtScheme (最小)
        fmtScheme = SubElement(themeElements, _a('fmtScheme'), {'name': 'Custom'})
        fillStyleLst = SubElement(fmtScheme, _a('fillStyleLst'))
        sf = SubElement(fillStyleLst, _a('solidFill'))
        SubElement(sf, _a('schemeClr'), {'val': 'phClr'})
        lnStyleLst = SubElement(fmtScheme, _a('lnStyleLst'))
        ln = SubElement(lnStyleLst, _a('ln'), {'w': '9525'})
        sf2 = SubElement(ln, _a('solidFill'))
        SubElement(sf2, _a('schemeClr'), {'val': 'phClr'})
        effectStyleLst = SubElement(fmtScheme, _a('effectStyleLst'))
        effectStyle = SubElement(effectStyleLst, _a('effectStyle'))
        SubElement(effectStyle, _a('effectLst'))
        bgFillStyleLst = SubElement(fmtScheme, _a('bgFillStyleLst'))
        sf3 = SubElement(bgFillStyleLst, _a('solidFill'))
        SubElement(sf3, _a('schemeClr'), {'val': 'phClr'})

        return tostring(root, xml_declaration=True, encoding='UTF-8').decode()


# ── 命名空间快捷函数 ──

def _p(tag: str) -> str:
    return '{%s}%s' % (NS['p'], tag)

def _a(tag: str) -> str:
    return '{%s}%s' % (NS['a'], tag)

def _r(attr: str) -> str:
    return '{%s}%s' % (NS['r'], attr)
