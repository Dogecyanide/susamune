# Moonshine Launcher FOXTROT

V2.3.0 pre-release · Build 1CF3F641

Latest feedback update:

- **Faster launcher startup:** the launcher opens your remembered Sunshine path and checks other devices when you select them. An unused USB drive no longer causes a startup wait.
- **One theme folder:** background.png and bgm.mp3 belong in **/Moonshine_Theme** at the root of the launcher's device. A missing folder is now created automatically once storage is ready; existing files stay intact and creation failure does not stop startup. The old app-local theme folder is no longer used.
- **Download-language correction:** the standard download now keeps all Moonshine menus English, including on JP. The Japanese download keeps its launcher Japanese regardless of game region and translates JP game menus; US/PAL game menus stay English. Standard Dolphin JP also stays English, with a separate Japanese JP patch. Sunshine's own language is unchanged.
- The Japanese download includes the runner's wording corrections and flag background. Some status messages and the built-in Guide body remain English. Keep the supplied **language.txt** beside boot.dol when updating. This launcher-language correction retains mod checksum **1CF3F641**.
- Fixed the false **Settings save: storage access denied** error when closing the menu. Real storage errors and read-only files still report a failure.
- Pause and Step yield to an exact longer shortcut, so **B+D-Up Reset** does not also activate **D-Up Pause**. Held gameplay inputs still work during frame advance.
- Turning **Ghost display Off** also hides its input panels. Turning it back On restores the selected input display.
- Repaired the missing **Gelato 5 Talk**, **Pinna 1 Talk/hits**, **Sirena 2 Reds / Noki 6 Reds button**, and **Spawn Shine** checkpoints, including Noki Hidden's bird and Gold Bird.
- Included a short feedback sheet, a full **RC1 test log** covering new and existing features, and a course checklist to divide the route tests among runners.

Use the matching launcher and game files from this package. **RC1_TESTING.md** is the full release check; **RC1_ROUTES.md** lists each route's checkpoints. **TESTING.md** is the short latest-fixes sheet.
