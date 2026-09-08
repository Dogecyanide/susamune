"""Run production state-load queue code with controlled binds, prompts and card IO."""

import ctypes as C
from pathlib import Path
import subprocess
import tempfile
import unittest

from test_practice_tape import function_source

ROOT = Path(__file__).resolve().parents[1]


class SavestateQueueTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        compiler = ROOT / "toolchain/clang++.exe"
        if not compiler.exists():
            raise unittest.SkipTest("Bundled Windows compiler required")
        cls.folder = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.folder.cleanup)
        source = r'''
typedef unsigned int u32;
enum { BIND_SAVESTATE_SAVE, BIND_SAVESTATE_LOAD, BIND_SAVESTATE_CYCLE,
       BIND_ATTEMPT_SHOW, BIND_ATTEMPT_ADD, BIND_COUNT };
enum { SETTING_ATTEMPT_COUNTER, SETTING_ATTEMPT_IN_STAGE_CONTROLS };
enum { CARD_ERROR_BUSY = -1 };
static u32 sActiveSlot, sPendingSlot, sPendingGeneration;
static bool sAwaitingLoadApproval;
static bool diskOwned;
static u32 generations[3], saveCalls, loadCalls, cycleCalls, feedbackCalls;
static u32 loadedSlot, loadedGeneration, pendingAtLoad;
struct Settings {
    bool values[2];
    bool getBool(int id) { return values[id]; }
} gSettings;
struct Binds {
    u32 pressed, values[BIND_COUNT];
    u32 get(int id) { return values[id]; }
    bool wasPressed(int id) { return (pressed & (1u << id)) != 0; }
} gBinds;
struct Card {
    bool busy;
    int getLastStatus() { return busy ? CARD_ERROR_BUSY : 0; }
} card;
static Card *gpCardManager;
namespace WarpWheel {
bool prompt, approved, requestNeedsPrompt;
bool takeSavestateLoadApproval() { bool out = approved; approved = false; return out; }
bool promptPending() { return prompt; }
bool requestSavestateLoad() { prompt = requestNeedsPrompt; return !prompt; }
}
#define SET_STATUS(text) ((void)0)
class SavestateManager {
public:
    bool mLoadPending;
    static bool diskBusy() { return diskOwned; }
    u32 mLoadWaitFrames;
    struct SlotInfo { u32 generation; };
    SlotInfo slotInfo(u32 slot) { return { generations[slot] }; }
    bool saveState() { ++saveCalls; return true; }
    bool loadSlot(u32 slot, u32 generation) {
        ++loadCalls; loadedSlot = slot; loadedGeneration = generation;
        pendingAtLoad = mLoadPending; return true;
    }
    bool cycleSlot() { ++cycleCalls; sActiveSlot = (sActiveSlot + 1) % 3; return true; }
    void feedback(const char *, const char *) { ++feedbackCalls; }
    void updateHook();
    void processPendingLoad();
} manager;
'''
        path = ROOT / "src/savestate.cpp"
        source += function_source(path, "void SavestateManager::updateHook()")
        source += function_source(path, "void SavestateManager::processPendingLoad()")
        source += r'''
#define API extern "C" __declspec(dllexport)
API void reset() {
    sActiveSlot = sPendingSlot = sPendingGeneration = 0;
    sAwaitingLoadApproval = manager.mLoadPending = false;
    diskOwned = false;
    manager.mLoadWaitFrames = 0;
    saveCalls = loadCalls = cycleCalls = feedbackCalls = 0;
    loadedSlot = loadedGeneration = pendingAtLoad = 0;
    gBinds.pressed = 0;
    for (u32 i = 0; i < BIND_COUNT; ++i) gBinds.values[i] = 1u << i;
    for (u32 i = 0; i < 3; ++i) generations[i] = 101 + i;
    gSettings.values[0] = gSettings.values[1] = false;
    WarpWheel::prompt = WarpWheel::approved = WarpWheel::requestNeedsPrompt = false;
    card.busy = false; gpCardManager = &card;
}
API void press(u32 value) { gBinds.pressed = value; }
API void select(u32 value) { sActiveSlot = value; }
API void generation(u32 slot, u32 value) { generations[slot] = value; }
API void promptMode(u32 value) { WarpWheel::requestNeedsPrompt = value != 0; }
API void approve() { WarpWheel::prompt = false; WarpWheel::approved = true; }
API void cancel() { WarpWheel::prompt = WarpWheel::approved = false; }
API void busy(u32 value) { card.busy = value != 0; }
API void disk(u32 value) { diskOwned = value != 0; }
API void noCard() { gpCardManager = 0; }
API void counter(u32 value) { gSettings.values[0] = gSettings.values[1] = value != 0; }
API void binding(u32 id, u32 value) { gBinds.values[id] = value; }
API void update() { manager.updateHook(); gBinds.pressed = 0; }
API void process() { manager.processPendingLoad(); }
API u32 get(u32 key) {
    switch (key) {
    case 0: return sActiveSlot;
    case 1: return manager.mLoadPending;
    case 2: return sAwaitingLoadApproval;
    case 3: return manager.mLoadWaitFrames;
    case 4: return saveCalls;
    case 5: return loadCalls;
    case 6: return cycleCalls;
    case 7: return feedbackCalls;
    case 8: return loadedSlot;
    case 9: return loadedGeneration;
    case 10: return pendingAtLoad;
    }
    return 0;
}
'''
        shim = Path(cls.folder.name) / "queue.cpp"
        shim.write_text(source, encoding="ascii")
        library = shim.with_suffix(".dll")
        subprocess.run([str(compiler), "--target=x86_64-pc-windows-msvc", "-shared",
                        "-nostdlib", "-fuse-ld=lld", "-Wl,/noentry", "-O2",
                        str(shim), "-o", str(library)], check=True)
        cls.lib = C.CDLL(str(library))
        cls.addClassCleanup(lambda: C.windll.kernel32.FreeLibrary(C.c_void_p(cls.lib._handle)))
        for name in ("reset", "approve", "cancel", "noCard", "update", "process"):
            getattr(cls.lib, name).argtypes = []
            getattr(cls.lib, name).restype = None
        for name in ("press", "select", "promptMode", "busy", "counter"):
            getattr(cls.lib, name).argtypes = [C.c_uint]
            getattr(cls.lib, name).restype = None
        for name in ("generation", "binding"):
            getattr(cls.lib, name).argtypes = [C.c_uint, C.c_uint]
            getattr(cls.lib, name).restype = None
        cls.lib.get.argtypes = [C.c_uint]
        cls.lib.get.restype = C.c_uint

    def setUp(self):
        self.lib.reset()

    def assert_loaded(self, slot, generation):
        self.assertEqual(self.lib.get(5), 1)
        self.assertEqual(self.lib.get(8), slot)
        self.assertEqual(self.lib.get(9), generation)
        self.assertEqual(self.lib.get(10), 0, "Queue must clear before the restore callback")
        self.lib.process()
        self.assertEqual(self.lib.get(5), 1, "A request must restore only once")

    def test_direct_load_pins_slot_and_generation_until_post_render(self):
        self.lib.select(1)
        self.lib.press(2)
        self.lib.update()
        self.assertEqual(self.lib.get(1), 1)
        self.assertEqual(self.lib.get(5), 0)
        self.lib.select(2)
        self.lib.generation(1, 999)
        self.lib.noCard()
        self.lib.process()
        self.assert_loaded(1, 102)

    def test_prompt_and_card_wait_keep_original_request(self):
        self.lib.select(2)
        self.lib.promptMode(1)
        self.lib.press(2)
        self.lib.update()
        self.assertEqual(self.lib.get(2), 1)
        self.assertEqual(self.lib.get(1), 0)
        self.lib.select(0)
        self.lib.press(7)
        self.lib.update()
        self.lib.process()
        self.assertEqual([self.lib.get(i) for i in (4, 5, 6)], [0, 0, 0])
        self.lib.approve()
        self.lib.press(7)
        self.lib.update()
        self.assertEqual(self.lib.get(2), 0)
        self.assertEqual(self.lib.get(1), 1)
        self.lib.busy(1)
        for _ in range(8):
            self.lib.press(7)
            self.lib.update()
            self.lib.process()
        self.assertEqual(self.lib.get(3), 8)
        self.assertEqual([self.lib.get(i) for i in (4, 5, 6)], [0, 0, 0])
        self.lib.select(1)
        self.lib.busy(0)
        self.lib.process()
        self.assert_loaded(2, 103)

    def test_cancelled_prompt_cannot_load_later_or_block_new_save(self):
        self.lib.promptMode(1)
        self.lib.press(2)
        self.lib.update()
        self.lib.cancel()
        self.lib.update()
        self.lib.process()
        self.assertEqual([self.lib.get(i) for i in (1, 2, 5)], [0, 0, 0])
        self.lib.approve()  # A stale approval has no owning request.
        self.lib.press(1)
        self.lib.update()
        self.lib.process()
        self.assertEqual(self.lib.get(4), 1)
        self.assertEqual(self.lib.get(5), 0)

    def test_card_timeout_drops_request_exactly_at_600_rendered_frames(self):
        self.lib.press(2)
        self.lib.update()
        self.lib.busy(1)
        for _ in range(599):
            self.lib.process()
        self.assertEqual(self.lib.get(1), 1)
        self.assertEqual(self.lib.get(7), 0)
        self.lib.process()
        self.assertEqual([self.lib.get(i) for i in (1, 3, 5, 7)], [0, 0, 0, 1])
        self.lib.busy(0)
        self.lib.process()
        self.assertEqual(self.lib.get(5), 0)

    def test_collision_priority_is_save_then_load_then_cycle(self):
        for pressed, calls in ((7, (1, 0, 0)), (6, (0, 1, 0)), (4, (0, 0, 1))):
            with self.subTest(pressed=pressed):
                self.lib.reset()
                self.lib.press(pressed)
                self.lib.update()
                self.lib.process()
                self.assertEqual(tuple(self.lib.get(i) for i in (4, 5, 6)), calls)

    def test_attempt_counter_owns_only_nonzero_colliding_binds(self):
        self.lib.counter(1)
        self.lib.binding(3, 1)  # Counter Show owns Save's combo.
        self.lib.press(7)
        self.lib.update()
        self.lib.process()
        self.assertEqual([self.lib.get(i) for i in (4, 5, 6)], [0, 1, 0])
        self.lib.reset()
        self.lib.counter(1)
        self.lib.binding(4, 2)  # Counter Add owns Load's combo.
        self.lib.press(6)
        self.lib.update()
        self.lib.process()
        self.assertEqual([self.lib.get(i) for i in (4, 5, 6)], [0, 0, 1])
        self.lib.reset()
        self.lib.counter(1)
        self.lib.binding(0, 0)
        self.lib.binding(3, 0)
        self.lib.press(1)
        self.lib.update()
        self.assertEqual(self.lib.get(4), 1)

    def test_disk_ownership_blocks_new_binds_and_preserves_a_queued_load(self):
        self.lib.disk(1)
        self.lib.press(7); self.lib.update(); self.lib.process()
        self.assertEqual([self.lib.get(i) for i in (4, 5, 6)], [0, 0, 0])
        self.lib.disk(0); self.lib.press(2); self.lib.update()
        self.lib.disk(1); self.lib.process()
        self.assertEqual([self.lib.get(i) for i in (1, 3, 5)], [1, 0, 0])
        self.lib.disk(0); self.lib.process()
        self.assert_loaded(0, 101)


if __name__ == "__main__":
    unittest.main()
