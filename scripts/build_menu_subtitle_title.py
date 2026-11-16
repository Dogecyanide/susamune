"""Render the fixed heading from the user's English retail cutscene font, preserving glyph metrics."""
import argparse
import hashlib
import mmap
from pathlib import Path
import struct
from PIL import Image
from inspect_rarc_asset import disc_files,decode_yaz0,rarc_files
ROOT=Path(__file__).resolve().parents[1]

def main():
    parser=argparse.ArgumentParser();parser.add_argument('iso',type=Path);args=parser.parse_args()
    with args.iso.open('rb') as f,mmap.mmap(f.fileno(),0,access=mmap.ACCESS_READ) as disc:
        offset,size=disc_files(disc)['data/subtitle.szs']
        font=rarc_files(decode_yaz0(disc[offset:offset+size]))['font/demo_font.bfn']
    chunks={};at=32
    while at<len(font):
        size=struct.unpack_from('>I',font,at+4)[0];chunks[font[at:at+4]]=font[at:at+size];at+=size
    glyph=chunks[b'GLY1'];widths=chunks[b'WID1'];mapping=chunks[b'MAP1']
    method,first,last=struct.unpack_from('>HHH',mapping,8)
    start,end,cw,ch,sheet,fmt,cols,rows,tw,th=struct.unpack_from('>HHHHIHHHHH',glyph,8)
    assert method==0 and first==32 and fmt==2 and tw==512 and th==512
    width_first=struct.unpack_from('>H',widths,8)[0]
    canvas=Image.new('RGBA',(400,ch));pen=0
    for char in 'MOONSHINE':
        code=ord(char)-first;left,advance=widths[12+2*(code-width_first):14+2*(code-width_first)]
        index=code-start;page=index//(cols*rows);index%=cols*rows
        x0=index%cols*cw;y0=index//cols*ch
        tile=Image.new('RGBA',(cw,ch))
        for y in range(ch):
            for x in range(cw):
                sx=x0+x;sy=y0+y
                value=glyph[32+page*sheet+((sy//4)*(tw//8)+sx//8)*32+(sy%4)*8+sx%8]
                intensity=(value&15)*17;alpha=(value>>4)*17
                tile.putpixel((x,y),(intensity,intensity,intensity,alpha))
        if pen:pen-=left
        canvas.alpha_composite(tile,(pen,0));pen+=advance+(left if not pen else 0)
    canvas=canvas.crop(canvas.getchannel('A').getbbox())
    w=(canvas.width+7)//8*8;h=(canvas.height+3)//4*4
    padded=Image.new('RGBA',(w,h));padded.alpha_composite(canvas)
    texture=bytearray(32+w*h);texture[:2]=bytes((2,2));struct.pack_into('>HH',texture,2,w,h)
    texture[20]=texture[21]=texture[24]=1;struct.pack_into('>I',texture,28,32)
    for y in range(h):
        for x in range(w):
            r,_,_,a=padded.getpixel((x,y));texture[32+((y//4)*(w//8)+x//8)*32+(y%4)*8+x%8]=(a>>4)<<4|r>>4
    packed=bytearray(b'Yaz0'+struct.pack('>I',len(texture))+bytes(8));at=0
    while at<len(texture):
        flag_at=len(packed);packed.append(0);flags=0
        for bit in range(8):
            if at==len(texture):break
            best=0;source=0
            for prior in range(max(0,at-4096),at):
                n=0
                while n<min(273,len(texture)-at) and texture[prior+n]==texture[at+n]:n+=1
                if n>best:best=n;source=prior
            if best>=3:
                distance=at-source-1
                if best>=18:packed+=bytes((distance>>8,distance&255,best-18))
                else:packed+=bytes((((best-2)<<4)|(distance>>8),distance&255))
                at+=best
            else:flags|=128>>bit;packed.append(texture[at]);at+=1
        packed[flag_at]=flags
    assert decode_yaz0(packed)==texture
    lines=['// Generated from retail demo_font.bfn by scripts/build_menu_subtitle_title.py.',
           '// Source SHA-256: '+hashlib.sha256(font).hexdigest(),
           '#include "susamune/menu_subtitle_title.hxx"','#include <JSystem/JKernel/JKRDecomp.hxx>','namespace MenuSubtitleTitle {',
           'void copy(void *destination) {','    static const unsigned char runs[] = {']
    lines += ['        '+','.join(str(v) for v in packed[i:i+24])+',' for i in range(0,len(packed),24)]
    lines += ['    };','    JKRDecomp::decodeSZS(const_cast<unsigned char *>(runs),static_cast<unsigned char *>(destination),Bytes,0);','}','}','']
    (ROOT/'src/menu_subtitle_title.cpp').write_text('\n'.join(lines))
    (ROOT/'include/susamune/menu_subtitle_title.hxx').write_text('#pragma once\nnamespace MenuSubtitleTitle {\nenum { Bytes = '+str(len(texture))+' };\nvoid copy(void *);\n}\n')
    out=ROOT/'build/pr38-evidence';out.mkdir(exist_ok=True)
    padded.save(out/'subtitle-title.png');print(dict(width=w,height=h,texture_bytes=len(texture),packed_bytes=len(packed)))

if __name__=='__main__':main()
