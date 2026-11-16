from pathlib import Path
import re
ROOT=Path(__file__).resolve().parents[1];P=ROOT
from test_ghost_trace_storage import writer_source as original_writer

def writer_source(root=P):
 source=original_writer(root)
 if '#define EXPORT_BOX' in source:return source
 source=source.replace('int GhostTraceStoragePending(void) {','static int exportPending(void);\nstatic void exportService(void);\nint GhostTraceStoragePending(void) {')
 export=(root/'launcher/kernel/GhostTraceExportStorage.inc').read_text()
 export=re.sub(r'^#include .*$', '',export,flags=re.M)
 export=export.replace('#define EXPORT_WRITER ((struct TraceExportWriter*)(MS_TRACE_CONTROL_PHYS+MS_TRACE_EXPORT_ARM_OFFSET))','static struct TraceExportWriter testExportWriter;\n#define EXPORT_WRITER (&testExportWriter)')
 export=export.replace('#define EXPORT_BOX ((volatile struct MsTraceExportMailbox*)(MS_TRACE_CONTROL_PHYS+MS_TRACE_EXPORT_MAILBOX_OFFSET))','static struct MsTraceExportMailbox testExportBox;\n#define EXPORT_BOX (&testExportBox)')
 export=export.replace('#define EXPORT_DATA ((unsigned char*)MS_TRACE_EXPORT_BUFFER_PHYS)','static unsigned char exportMemory[MS_TRACE_EXPORT_BUFFER_BYTES+64] __attribute__((aligned(32)));\n#define EXPORT_DATA (exportMemory+32)')
 return '#include "susamune/ghost_trace_export.h"\nvoid*memmove(void*,const void*,__SIZE_TYPE__);\n'+source+'\n'+export
