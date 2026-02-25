"""合并多个单 slide PPTX 文件为一个（仅用标准库 zipfile + re）。"""
import os
import re
import shutil
import zipfile


_SLIDE_CT = ('application/vnd.openxmlformats-officedocument'
             '.presentationml.slide+xml')
_SLIDE_REL_TYPE = ('http://schemas.openxmlformats.org/officeDocument'
                   '/2006/relationships/slide')


def merge_pptx(pptx_paths: list, output_path: str) -> str:
    """
    将多个 PPTX（每个通常只含 1 张 slide）合并为一个。

    Parameters
    ----------
    pptx_paths : list[str]
        各临时 PPTX 文件路径。
    output_path : str
        输出路径。

    Returns
    -------
    str  实际写入的文件路径，失败返回空字符串。
    """
    valid = [p for p in pptx_paths if p and os.path.isfile(p)]
    if not valid:
        return ''

    out_dir = os.path.dirname(output_path)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)

    if len(valid) == 1:
        shutil.copy2(valid[0], output_path)
        return output_path

    # 以第一个 PPTX 为基础
    shutil.copy2(valid[0], output_path)
    for src in valid[1:]:
        _append_slides(output_path, src)
    return output_path


# ── 内部实现 ──

def _max_int(pattern, names):
    """从文件名列表中提取最大数字编号。"""
    nums = []
    for n in names:
        m = re.match(pattern, n)
        if m:
            nums.append(int(m.group(1)))
    return max(nums) if nums else 0


def _append_slides(base_path: str, src_path: str):
    """将 src_path 中的所有 slide 追加到 base_path（原地修改）。"""

    # ── 读取 source ──
    with zipfile.ZipFile(src_path, 'r') as zs:
        src_files = {n: zs.read(n) for n in zs.namelist()}

    src_slides = sorted(
        n for n in src_files
        if re.match(r'ppt/slides/slide\d+\.xml$', n)
    )
    if not src_slides:
        return

    # ── 读取 base ──
    with zipfile.ZipFile(base_path, 'r') as zb:
        base = {n: zb.read(n) for n in zb.namelist()}

    # ── 各种编号计数器 ──
    next_slide = _max_int(r'ppt/slides/slide(\d+)\.xml$', base) + 1
    next_media = _max_int(r'ppt/media/image(\d+)', base) + 1

    pres_rels_key = 'ppt/_rels/presentation.xml.rels'
    pres_rels_text = base[pres_rels_key].decode('utf-8')
    next_rid = max(
        (int(m.group(1)) for m in re.finditer(r'Id="rId(\d+)"', pres_rels_text)),
        default=0
    ) + 1

    pres_text = base['ppt/presentation.xml'].decode('utf-8')
    next_sid = max(
        (int(m.group(1)) for m in re.finditer(r'\bid="(\d+)"', pres_text)),
        default=255
    ) + 1

    ct_text = base['[Content_Types].xml'].decode('utf-8')

    # ── 逐 slide 处理 ──
    new_files = {}
    ct_entries = []
    rel_entries = []
    sid_entries = []

    for src_slide_path in src_slides:
        new_slide_xml = f'ppt/slides/slide{next_slide}.xml'
        new_files[new_slide_xml] = src_files[src_slide_path]

        # slide rels
        src_rels_path = src_slide_path.replace(
            'ppt/slides/', 'ppt/slides/_rels/'
        ).replace('.xml', '.xml.rels')

        if src_rels_path in src_files:
            rels_text = src_files[src_rels_path].decode('utf-8')

            # 重命名 media 引用，避免与 base 冲突
            def _rename_media(m):
                nonlocal next_media
                old_name = m.group(1)
                ext = os.path.splitext(old_name)[1]
                new_name = f'image{next_media}{ext}'
                old_full = f'ppt/media/{old_name}'
                new_full = f'ppt/media/{new_name}'
                if old_full in src_files:
                    new_files[new_full] = src_files[old_full]
                next_media += 1
                return f'Target="../media/{new_name}"'

            rels_text = re.sub(
                r'Target="\.\./media/([^"]+)"', _rename_media, rels_text
            )

            # slideLayout 统一指向 base 的 layout1
            rels_text = re.sub(
                r'Target="\.\./slideLayouts/slideLayout\d+\.xml"',
                'Target="../slideLayouts/slideLayout1.xml"',
                rels_text
            )

            new_rels_xml = f'ppt/slides/_rels/slide{next_slide}.xml.rels'
            new_files[new_rels_xml] = rels_text.encode('utf-8')

        rid = f'rId{next_rid}'
        ct_entries.append(
            f'<Override PartName="/ppt/slides/slide{next_slide}.xml"'
            f' ContentType="{_SLIDE_CT}"/>'
        )
        rel_entries.append(
            f'<Relationship Id="{rid}" Type="{_SLIDE_REL_TYPE}"'
            f' Target="slides/slide{next_slide}.xml"/>'
        )
        sid_entries.append((next_sid, rid))

        next_slide += 1
        next_rid += 1
        next_sid += 1

    # ── 更新 [Content_Types].xml ──
    insert_ct = '\n'.join(ct_entries)
    ct_text = ct_text.replace('</Types>', insert_ct + '\n</Types>')
    base['[Content_Types].xml'] = ct_text.encode('utf-8')

    # ── 更新 ppt/_rels/presentation.xml.rels ──
    insert_rel = '\n'.join(rel_entries)
    pres_rels_text = pres_rels_text.replace(
        '</Relationships>', insert_rel + '\n</Relationships>'
    )
    base[pres_rels_key] = pres_rels_text.encode('utf-8')

    # ── 更新 ppt/presentation.xml ──
    sld_match = re.search(r'<(\w+):sldId\s', pres_text)
    p_prefix = sld_match.group(1) if sld_match else 'p'

    sld_xml = '\n'.join(
        f'<{p_prefix}:sldId id="{sid}" r:id="{rid}"/>'
        for sid, rid in sid_entries
    )

    close_pat = rf'</{p_prefix}:sldIdLst>'
    close_m = re.search(close_pat, pres_text)
    if close_m:
        pos = close_m.start()
        pres_text = pres_text[:pos] + sld_xml + '\n' + pres_text[pos:]
    else:
        # 处理自闭合 <p:sldIdLst/>
        self_close = re.search(rf'<{p_prefix}:sldIdLst\s*/>', pres_text)
        if self_close:
            pres_text = (
                pres_text[:self_close.start()]
                + f'<{p_prefix}:sldIdLst>' + sld_xml
                + f'</{p_prefix}:sldIdLst>'
                + pres_text[self_close.end():]
            )

    base['ppt/presentation.xml'] = pres_text.encode('utf-8')

    # ── 写回 ──
    with zipfile.ZipFile(base_path, 'w', zipfile.ZIP_DEFLATED) as zf:
        for name, data in base.items():
            zf.writestr(name, data)
        for name, data in new_files.items():
            if name not in base:
                zf.writestr(name, data)
