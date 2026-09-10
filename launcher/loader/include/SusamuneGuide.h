#ifndef __SUSAMUNE_GUIDE_H__
#define __SUSAMUNE_GUIDE_H__

#define SUSAMUNE_GUIDE_ROWS 14

int SusamuneGuideTopicCount(void);
const char *SusamuneGuideTitle(int topic);
int SusamuneGuideLineCount(int topic);
const char *SusamuneGuideLine(int topic, int line);
int SusamuneGuideScroll(int first, int lines, int delta);

#endif
