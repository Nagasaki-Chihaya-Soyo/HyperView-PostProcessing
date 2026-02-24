"""
Minimal PPTX builder using only Python stdlib (zipfile + xml).
Creates a presentation with one image + caption per slide.
No external dependencies required.
"""
import os
import zipfile
import struct

# EMU constants: 1 inch = 914400 EMU
SLIDE_W = 9144000   # 10 inches
SLIDE_H = 6858000   # 7.5 inches

# Image area (leave bottom 15% for caption)
IMG_X = 0
IMG_Y = 0
IMG_W = SLIDE_W
IMG_H = 5829300     # ~6.375 inches

# Caption text box
TXT_X = 457200      # 0.5 inch
TXT_Y = 5943600     # below image
TXT_W = 8229600     # 9 inches
TXT_H = 685800      # 0.75 inch

NS = {
    'a': 'http://schemas.openxmlformats.org/drawingml/2006/main',
    'r': 'http://schemas.openxmlformats.org/officeDocument/2006/relationships',
    'p': 'http://schemas.openxmlformats.org/presentationml/2006/main',
}


def _get_png_dimensions(path):
    """Read width/height from PNG header."""
    try:
        with open(path, 'rb') as f:
            f.read(16)  # skip signature + IHDR chunk header
            w = struct.unpack('>I', f.read(4))[0]
            h = struct.unpack('>I', f.read(4))[0]
            return w, h
    except Exception:
        return 1920, 1080


def _content_types_xml(n_slides):
    parts = []
    for i in range(1, n_slides + 1):
        parts.append(f'  <Override PartName="/ppt/slides/slide{i}.xml" '
                     f'ContentType="application/vnd.openxmlformats-officedocument.presentationml.slide+xml"/>')
    return f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Default Extension="png" ContentType="image/png"/>
  <Default Extension="jpg" ContentType="image/jpeg"/>
  <Default Extension="jpeg" ContentType="image/jpeg"/>
  <Override PartName="/ppt/presentation.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.presentation.main+xml"/>
  <Override PartName="/ppt/slideMasters/slideMaster1.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.slideMaster+xml"/>
  <Override PartName="/ppt/slideLayouts/slideLayout1.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.slideLayout+xml"/>
  <Override PartName="/ppt/theme/theme1.xml" ContentType="application/vnd.openxmlformats-officedocument.theme+xml"/>
{chr(10).join(parts)}
</Types>'''


def _root_rels():
    return '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="ppt/presentation.xml"/>
</Relationships>'''


def _presentation_xml(n_slides):
    slide_list = '\n'.join(
        f'    <p:sldId id="{256 + i}" r:id="rId{i + 2}"/>'
        for i in range(n_slides)
    )
    return f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<p:presentation xmlns:a="{NS['a']}" xmlns:r="{NS['r']}" xmlns:p="{NS['p']}">
  <p:sldMasterIdLst>
    <p:sldMasterId id="2147483648" r:id="rId1"/>
  </p:sldMasterIdLst>
  <p:sldIdLst>
{slide_list}
  </p:sldIdLst>
  <p:sldSz cx="{SLIDE_W}" cy="{SLIDE_H}"/>
  <p:notesSz cx="{SLIDE_H}" cy="{SLIDE_W}"/>
</p:presentation>'''


def _presentation_rels(n_slides):
    rels = [
        '  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideMaster" Target="slideMasters/slideMaster1.xml"/>'
    ]
    for i in range(n_slides):
        rels.append(
            f'  <Relationship Id="rId{i + 2}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slide" Target="slides/slide{i + 1}.xml"/>'
        )
    rels.append(
        f'  <Relationship Id="rId{n_slides + 2}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/theme" Target="theme/theme1.xml"/>'
    )
    return f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
{chr(10).join(rels)}
</Relationships>'''


def _slide_master_xml():
    return f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<p:sldMaster xmlns:a="{NS['a']}" xmlns:r="{NS['r']}" xmlns:p="{NS['p']}">
  <p:cSld><p:spTree><p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr><p:grpSpPr/></p:spTree></p:cSld>
  <p:clrMap bg1="lt1" tx1="dk1" bg2="lt2" tx2="dk2" accent1="accent1" accent2="accent2" accent3="accent3" accent4="accent4" accent5="accent5" accent6="accent6" hlink="hlink" folHlink="folHlink"/>
  <p:sldLayoutIdLst><p:sldLayoutId id="2147483649" r:id="rId1"/></p:sldLayoutIdLst>
</p:sldMaster>'''


def _slide_master_rels():
    return '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideLayout" Target="../slideLayouts/slideLayout1.xml"/>
  <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/theme" Target="../theme/theme1.xml"/>
</Relationships>'''


def _slide_layout_xml():
    return f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<p:sldLayout xmlns:a="{NS['a']}" xmlns:r="{NS['r']}" xmlns:p="{NS['p']}" type="blank">
  <p:cSld><p:spTree><p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr><p:grpSpPr/></p:spTree></p:cSld>
</p:sldLayout>'''


def _slide_layout_rels():
    return '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideMaster" Target="../slideMasters/slideMaster1.xml"/>
</Relationships>'''


def _theme_xml():
    return f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<a:theme xmlns:a="{NS['a']}" name="Default">
  <a:themeElements>
    <a:clrScheme name="Office">
      <a:dk1><a:sysClr val="windowText" lastClr="000000"/></a:dk1>
      <a:lt1><a:sysClr val="window" lastClr="FFFFFF"/></a:lt1>
      <a:dk2><a:srgbClr val="44546A"/></a:dk2>
      <a:lt2><a:srgbClr val="E7E6E6"/></a:lt2>
      <a:accent1><a:srgbClr val="4472C4"/></a:accent1>
      <a:accent2><a:srgbClr val="ED7D31"/></a:accent2>
      <a:accent3><a:srgbClr val="A5A5A5"/></a:accent3>
      <a:accent4><a:srgbClr val="FFC000"/></a:accent4>
      <a:accent5><a:srgbClr val="5B9BD5"/></a:accent5>
      <a:accent6><a:srgbClr val="70AD47"/></a:accent6>
      <a:hlink><a:srgbClr val="0563C1"/></a:hlink>
      <a:folHlink><a:srgbClr val="954F72"/></a:folHlink>
    </a:clrScheme>
    <a:fontScheme name="Office">
      <a:majorFont><a:latin typeface="Calibri Light"/><a:ea typeface=""/><a:cs typeface=""/></a:majorFont>
      <a:minorFont><a:latin typeface="Calibri"/><a:ea typeface=""/><a:cs typeface=""/></a:minorFont>
    </a:fontScheme>
    <a:fmtScheme name="Office">
      <a:fillStyleLst><a:solidFill><a:schemeClr val="phClr"/></a:solidFill><a:solidFill><a:schemeClr val="phClr"/></a:solidFill><a:solidFill><a:schemeClr val="phClr"/></a:solidFill></a:fillStyleLst>
      <a:lnStyleLst><a:ln w="6350"><a:solidFill><a:schemeClr val="phClr"/></a:solidFill></a:ln><a:ln w="6350"><a:solidFill><a:schemeClr val="phClr"/></a:solidFill></a:ln><a:ln w="6350"><a:solidFill><a:schemeClr val="phClr"/></a:solidFill></a:ln></a:lnStyleLst>
      <a:effectStyleLst><a:effectStyle><a:effectLst/></a:effectStyle><a:effectStyle><a:effectLst/></a:effectStyle><a:effectStyle><a:effectLst/></a:effectStyle></a:effectStyleLst>
      <a:bgFillStyleLst><a:solidFill><a:schemeClr val="phClr"/></a:solidFill><a:solidFill><a:schemeClr val="phClr"/></a:solidFill><a:solidFill><a:schemeClr val="phClr"/></a:solidFill></a:bgFillStyleLst>
    </a:fmtScheme>
  </a:themeElements>
</a:theme>'''


def _slide_xml(slide_idx, label):
    """Generate slide XML with one image filling most of the slide and a caption below."""
    return f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<p:sld xmlns:a="{NS['a']}" xmlns:r="{NS['r']}" xmlns:p="{NS['p']}">
  <p:cSld>
    <p:spTree>
      <p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr>
      <p:grpSpPr/>
      <p:pic>
        <p:nvPicPr>
          <p:cNvPr id="2" name="Image{slide_idx}"/>
          <p:cNvPicPr><a:picLocks noChangeAspect="1"/></p:cNvPicPr>
          <p:nvPr/>
        </p:nvPicPr>
        <p:blipFill>
          <a:blip r:embed="rId2"/>
          <a:stretch><a:fillRect/></a:stretch>
        </p:blipFill>
        <p:spPr>
          <a:xfrm>
            <a:off x="{IMG_X}" y="{IMG_Y}"/>
            <a:ext cx="{IMG_W}" cy="{IMG_H}"/>
          </a:xfrm>
          <a:prstGeom prst="rect"><a:avLst/></a:prstGeom>
        </p:spPr>
      </p:pic>
      <p:sp>
        <p:nvSpPr>
          <p:cNvPr id="3" name="Caption{slide_idx}"/>
          <p:cNvSpPr txBox="1"/>
          <p:nvPr/>
        </p:nvSpPr>
        <p:spPr>
          <a:xfrm>
            <a:off x="{TXT_X}" y="{TXT_Y}"/>
            <a:ext cx="{TXT_W}" cy="{TXT_H}"/>
          </a:xfrm>
          <a:prstGeom prst="rect"><a:avLst/></a:prstGeom>
        </p:spPr>
        <p:txBody>
          <a:bodyPr wrap="square" rtlCol="0" anchor="ctr"/>
          <a:p>
            <a:pPr algn="ctr"/>
            <a:r>
              <a:rPr lang="en-US" sz="1400" b="1" dirty="0"/>
              <a:t>{_xml_escape(label)}</a:t>
            </a:r>
          </a:p>
        </p:txBody>
      </p:sp>
    </p:spTree>
  </p:cSld>
</p:sld>'''


def _slide_rels(slide_idx):
    return f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideLayout" Target="../slideLayouts/slideLayout1.xml"/>
  <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" Target="../media/image{slide_idx}.png"/>
</Relationships>'''


def _xml_escape(s):
    return s.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;').replace('"', '&quot;')


def build_pptx(slides, output_path):
    """
    Build a PPTX file from captured slide images.

    Args:
        slides: list of dicts with keys 'image_path' (str) and 'label' (str)
        output_path: path for the output .pptx file

    Returns:
        output_path on success, None on failure
    """
    if not slides:
        return None

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    n = len(slides)

    with zipfile.ZipFile(output_path, 'w', zipfile.ZIP_DEFLATED) as zf:
        zf.writestr('[Content_Types].xml', _content_types_xml(n))
        zf.writestr('_rels/.rels', _root_rels())
        zf.writestr('ppt/presentation.xml', _presentation_xml(n))
        zf.writestr('ppt/_rels/presentation.xml.rels', _presentation_rels(n))
        zf.writestr('ppt/slideMasters/slideMaster1.xml', _slide_master_xml())
        zf.writestr('ppt/slideMasters/_rels/slideMaster1.xml.rels', _slide_master_rels())
        zf.writestr('ppt/slideLayouts/slideLayout1.xml', _slide_layout_xml())
        zf.writestr('ppt/slideLayouts/_rels/slideLayout1.xml.rels', _slide_layout_rels())
        zf.writestr('ppt/theme/theme1.xml', _theme_xml())

        for i, slide in enumerate(slides, 1):
            zf.writestr(f'ppt/slides/slide{i}.xml', _slide_xml(i, slide['label']))
            zf.writestr(f'ppt/slides/_rels/slide{i}.xml.rels', _slide_rels(i))

            img_path = slide['image_path']
            if os.path.isfile(img_path):
                with open(img_path, 'rb') as img_f:
                    zf.writestr(f'ppt/media/image{i}.png', img_f.read())

    return output_path
