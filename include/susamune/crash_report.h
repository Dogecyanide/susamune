#ifndef SUSAMUNE_CRASH_REPORT_H
#define SUSAMUNE_CRASH_REPORT_H

#include "susamune/mem2_map.h"

#define SUSAMUNE_CRASH_MAGIC              0x53435248u  /* 'SCRH' */
#define SUSAMUNE_CRASH_VERSION            1u
#define SUSAMUNE_CRASH_REPORT_SIZE        0x800u

#define SUSAMUNE_CRASH_STATE_DISABLED     0u
#define SUSAMUNE_CRASH_STATE_ARMED        1u
#define SUSAMUNE_CRASH_STATE_WRITING      2u
#define SUSAMUNE_CRASH_STATE_READY        3u

#define SUSAMUNE_CRASH_FLAG_STACK         (1u << 0)
#define SUSAMUNE_CRASH_FLAG_PC_WINDOW     (1u << 1)
#define SUSAMUNE_CRASH_FLAG_LR_WINDOW     (1u << 2)
#define SUSAMUNE_CRASH_FLAG_DIRECTOR      (1u << 3)
#define SUSAMUNE_CRASH_FLAG_MARIO         (1u << 4)

#define SUSAMUNE_CRASH_BREADCRUMB_COUNT   16u
#define SUSAMUNE_CRASH_BACKTRACE_COUNT    32u
#define SUSAMUNE_CRASH_STACK_SIZE         512u
#define SUSAMUNE_CRASH_CODE_WINDOW_SIZE   64u
#define SUSAMUNE_CRASH_DIRECTOR_SIZE      320u
#define SUSAMUNE_CRASH_MARIO_SIZE         128u

#define SUSAMUNE_CRASH_EVENT_APP_INIT       1u
#define SUSAMUNE_CRASH_EVENT_CONTEXT        2u
#define SUSAMUNE_CRASH_EVENT_SETUP_ENTER    3u
#define SUSAMUNE_CRASH_EVENT_SETUP_RETURN   4u
#define SUSAMUNE_CRASH_EVENT_STAGE_READY    5u
#define SUSAMUNE_CRASH_EVENT_PRACTICE       6u
#define SUSAMUNE_CRASH_EVENT_REPLAY         7u
#define SUSAMUNE_CRASH_EVENT_SAVESTATE      8u
#define SUSAMUNE_CRASH_EVENT_GHOST          9u
#define SUSAMUNE_CRASH_EVENT_STORAGE       10u
#define SUSAMUNE_CRASH_EVENT_DRAW          11u

#define SUSAMUNE_CRASH_CORE_MAGIC       0x53434352u /* 'SCCR' */
#define SUSAMUNE_CRASH_CORE_VERSION     1u
#define SUSAMUNE_CRASH_CORE_OFFSET      0x800u
#define SUSAMUNE_CRASH_CORE_SIZE        0x200u
#define SUSAMUNE_CRASH_ACK_OFFSET       0xA00u
#define SUSAMUNE_CRASH_ACK_MAGIC        0x5343414bu /* 'SCAK' */
#define SUSAMUNE_CRASH_ACK_UNAVAILABLE  1u
#define SUSAMUNE_CRASH_ACK_PENDING      2u
#define SUSAMUNE_CRASH_ACK_SAVED        3u
#define SUSAMUNE_CRASH_ACK_FAILED       4u
#define SUSAMUNE_CRASH_ACK_CORE_ONLY    5u
#define SUSAMUNE_CRASH_SAVED_CORE       1u
#define SUSAMUNE_CRASH_SAVED_FULL       2u
#define SUSAMUNE_CRASH_SAVED_TEXT       4u

struct SusamuneCrashBreadcrumb {
    unsigned int event;
    unsigned int timeBaseHigh;
    unsigned int timeBaseLow;
    unsigned int arg0;
    unsigned int arg1;
};

struct SusamuneCrashFrame {
    unsigned int stackPointer;
    unsigned int returnAddress;
};

struct SusamuneCrashReport {
    /* ARM initialises this line; the PPC publishes state READY last. */
    unsigned int   magic;
    unsigned short version;
    unsigned short reportSize;
    unsigned int   state;
    unsigned int   captureSeq;
    unsigned int   checksum;
    unsigned int   gameId;
    unsigned int   modFileCrc32;
    unsigned int   modFileSize;

    unsigned int   modCodeSize;
    unsigned int   modWriteCount;
    unsigned int   arenaReserve;
    unsigned short exception;
    unsigned short captureFlags;
    unsigned int   dsisr;
    unsigned int   dar;
    unsigned int   timeBaseHigh;
    unsigned int   timeBaseLow;

    unsigned int gpr[32];
    unsigned int cr;
    unsigned int lr;
    unsigned int ctr;
    unsigned int xer;
    unsigned int srr0;
    unsigned int srr1;
    unsigned short contextMode;
    unsigned short contextState;
    unsigned int currentThread;

    unsigned int appAddress;
    unsigned int appDirector;
    unsigned int appHeap;
    unsigned int appContext;
    unsigned int prevScene;
    unsigned int currentScene;
    unsigned int nextScene;
    unsigned int cutSceneId;
    unsigned int marDirector;
    unsigned int mario;
    unsigned int camera;
    unsigned int directorReady;
    unsigned int directorStateAreaEpisode;
    unsigned int directorGameState;
    unsigned int directorDemoStates;
    unsigned int directorCollectedShine;
    unsigned int breadcrumbSeq;
    unsigned int breadcrumbCount;

    struct SusamuneCrashBreadcrumb
        breadcrumbs[SUSAMUNE_CRASH_BREADCRUMB_COUNT];
    struct SusamuneCrashFrame backtrace[SUSAMUNE_CRASH_BACKTRACE_COUNT];

    unsigned int stackBase;
    unsigned int stackSize;
    unsigned char stack[SUSAMUNE_CRASH_STACK_SIZE];

    unsigned int pcWindowBase;
    unsigned int pcWindowSize;
    unsigned char pcWindow[SUSAMUNE_CRASH_CODE_WINDOW_SIZE];
    unsigned int lrWindowBase;
    unsigned int lrWindowSize;
    unsigned char lrWindow[SUSAMUNE_CRASH_CODE_WINDOW_SIZE];

    unsigned int directorWindowBase;
    unsigned short directorWindowSize;
    unsigned short reserved0;
    unsigned char directorWindow[SUSAMUNE_CRASH_DIRECTOR_SIZE];
    unsigned int marioWindowBase;
    unsigned short marioWindowSize;
    unsigned short reserved1;
    unsigned char marioWindow[SUSAMUNE_CRASH_MARIO_SIZE];

    unsigned char reserved[48];
};

/* Immutable once READY, even if optional full capture faults afterwards. */
struct SusamuneCrashCore {
    unsigned int magic;
    unsigned short version;
    unsigned short reportSize;
    unsigned int state;
    unsigned int captureSeq;
    unsigned int checksum;
    unsigned int gameId;
    unsigned int modFileCrc32;
    unsigned int exception;
    unsigned int gpr[32];
    unsigned int cr, lr, ctr, xer, srr0, srr1, dsisr, dar;
    unsigned int appContext, currentScene, prevScene, nextScene;
    unsigned int timeBaseHigh, timeBaseLow, lastEvent, lastArg0;
    unsigned int lastArg1, contextValid;
    char build[64];
    unsigned char reserved[216];
};

/* ARM owns this line; PPC only invalidates/reads it. */
struct SusamuneCrashAck {
    unsigned int magic, captureSeq, status, error;
    unsigned int attempts, savedFlags, reserved[2];
};

#define SUSAMUNE_CRASH_CORE_PPC_PTR ((struct SusamuneCrashCore *) \
    (SUSAMUNE_MEM2_CRASH_PPC_BASE + SUSAMUNE_CRASH_CORE_OFFSET))
#define SUSAMUNE_CRASH_CORE_PHYS_PTR ((struct SusamuneCrashCore *) \
    (SUSAMUNE_MEM2_CRASH_PHYS_BASE + SUSAMUNE_CRASH_CORE_OFFSET))
#define SUSAMUNE_CRASH_ACK_PPC_PTR ((struct SusamuneCrashAck *) \
    (SUSAMUNE_MEM2_CRASH_PPC_BASE + SUSAMUNE_CRASH_ACK_OFFSET))
#define SUSAMUNE_CRASH_ACK_PHYS_PTR ((struct SusamuneCrashAck *) \
    (SUSAMUNE_MEM2_CRASH_PHYS_BASE + SUSAMUNE_CRASH_ACK_OFFSET))

typedef char susamune_crash_core_size_check[
    (sizeof(struct SusamuneCrashCore) == SUSAMUNE_CRASH_CORE_SIZE) ? 1 : -1];
typedef char susamune_crash_ack_size_check[
    (sizeof(struct SusamuneCrashAck) == 32) ? 1 : -1];
typedef char susamune_crash_regions_check[
    (SUSAMUNE_CRASH_REPORT_SIZE <= SUSAMUNE_CRASH_CORE_OFFSET &&
     SUSAMUNE_CRASH_CORE_OFFSET + SUSAMUNE_CRASH_CORE_SIZE <=
        SUSAMUNE_CRASH_ACK_OFFSET &&
     SUSAMUNE_CRASH_ACK_OFFSET + 32 <= SUSAMUNE_MEM2_CRASH_SIZE) ? 1 : -1];

#define SUSAMUNE_CRASH_PPC_PTR \
    ((struct SusamuneCrashReport *)SUSAMUNE_MEM2_CRASH_PPC_BASE)
#define SUSAMUNE_CRASH_PHYS_PTR \
    ((struct SusamuneCrashReport *)SUSAMUNE_MEM2_CRASH_PHYS_BASE)

typedef char susamune_crash_header_line_check[
    (__builtin_offsetof(struct SusamuneCrashReport, modCodeSize) == 32) ? 1 : -1];
typedef char susamune_crash_gpr_check[
    (__builtin_offsetof(struct SusamuneCrashReport, gpr) == 64) ? 1 : -1];
typedef char susamune_crash_size_check[
    (sizeof(struct SusamuneCrashReport) == SUSAMUNE_CRASH_REPORT_SIZE) ? 1 : -1];
typedef char susamune_crash_mailbox_check[
    (sizeof(struct SusamuneCrashReport) <= SUSAMUNE_MEM2_CRASH_SIZE) ? 1 : -1];

#endif /* SUSAMUNE_CRASH_REPORT_H */
