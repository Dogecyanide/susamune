"""Run JP draw conversion and width calculation with a sparse retail-font stub."""
import os
from pathlib import Path
import subprocess,tempfile,unittest
from test_native_timer_creation import function
ROOT=Path(__file__).resolve().parents[1]
class JapanesePunctuationTests(unittest.TestCase):
    def test_punctuation_and_width_agree(self):
        source=(ROOT/'src/menu.cpp').read_text()
        for label in ('Inputs & movement','HUD & messages','Position & camera','Layout & colours'):
            self.assertNotIn(label,source)
        code=r"""
#include <cassert>
#include <cstring>
using u32=unsigned;using u8=unsigned char;
#define SUSAMUNE_VERSION_JP 1
#define SUSAMUNE_MENU_TEXT_SIZE 512
struct JUTFont {
 struct TWidth {u8 mWidth,mMargin;};
 bool isLeadByte(int c){return (c>=0x81&&c<=0x9f)||(c>=0xe0&&c<=0xfc);}
 void getWidthEntry(int c,TWidth*t){t->mMargin=0;t->mWidth=c=='/'||c=='&'?40:c==0x815e?7:c==0x8195?9:10;}
};
static JUTFont font,*sFont=&font;static bool sFontFixed=false;
static int sFontFixedW=12,sFontWidth=10,sCharSpacing=0;
static char sFontSafeText[SUSAMUNE_MENU_TEXT_SIZE];
namespace JapaneseUi {const char*text(const char*s){return s;}int width(const char*,int){return -1;}}
struct Menu {static int textWidth(const char*,int);};
"""
        code+=function(source,'fontSafeText')+function(source[source.index('int Menu::textWidth('):],'Menu::textWidth')
        code+=r"""
int main(){
 assert(!strcmp(fontSafeText("Inputs / movement"),"Inputs \x81\x5e movement"));
 assert(!strcmp(fontSafeText("L/R \x81\x95 A/B"),"L\x81\x5eR \x81\x95 A\x81\x5e" "B"));
 const char*buttons="\x81\x83\x81\x5e\x81\x84";
 assert(fontSafeText(buttons)==buttons);
 assert(Menu::textWidth("L/R \x81\x95 A/B",10)==83);
 assert(Menu::textWidth("L/R \x81\x95 A/B",10)==Menu::textWidth(fontSafeText("L/R \x81\x95 A/B"),10));
 char boundary[512];memset(boundary,'x',510);boundary[509]='/';boundary[510]=0;
 assert(strlen(fontSafeText(boundary))==511);
 boundary[510]='x';boundary[511]=0;assert(fontSafeText(boundary)==boundary);
 assert(!strcmp(fontSafeText("Plain text"),"Plain text"));
}
"""
        with tempfile.TemporaryDirectory(prefix='jp-punctuation-') as temp:
            p=Path(temp);(p/'test.cpp').write_text(code)
            compiler='C:/msys64/mingw64/bin/g++.exe' if os.name=='nt' else 'g++'
            env=dict(os.environ,PATH=str(Path(compiler).parent)+os.pathsep+os.environ.get('PATH',''))
            result=subprocess.run([compiler,'-std=c++17','-static',str(p/'test.cpp'),'-o',str(p/'test.exe')],capture_output=True,env=env)
            self.assertEqual(result.returncode,0,result.stderr.decode())
            subprocess.run([str(p/'test.exe')],check=True,capture_output=True)
if __name__=='__main__':unittest.main()
