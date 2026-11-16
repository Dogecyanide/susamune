#ifndef MOONSHINE_MEM2_AUDIT_H
#define MOONSHINE_MEM2_AUDIT_H

#if MOONSHINE_MEM2_DIAGNOSTICS
void MoonshineMem2AuditCapture(unsigned int phase);
void MoonshineMem2AuditWrite(const char *device);
#else
#define MoonshineMem2AuditCapture(phase) ((void)0)
#define MoonshineMem2AuditWrite(device) ((void)0)
#endif
#endif
