#include "SusamuneGuide.h"

typedef struct
{
	unsigned short title;
	unsigned short first;
	unsigned short count;
} GuideTopic;

#include "susamune_guide_data.inc"

int SusamuneGuideTopicCount(void)
{
	return sizeof(kGuideTopics) / sizeof(kGuideTopics[0]);
}

const char *SusamuneGuideTitle(int topic)
{
	if (topic < 0 || topic >= SusamuneGuideTopicCount())
		return "";
	return kGuideText + kGuideTopics[topic].title;
}

int SusamuneGuideLineCount(int topic)
{
	if (topic < 0 || topic >= SusamuneGuideTopicCount())
		return 0;
	return kGuideTopics[topic].count;
}

const char *SusamuneGuideLine(int topic, int line)
{
	if (line < 0 || line >= SusamuneGuideLineCount(topic))
		return "";
	return kGuideText + kGuideLines[kGuideTopics[topic].first + line];
}

int SusamuneGuideScroll(int first, int lines, int delta)
{
	int last = lines > SUSAMUNE_GUIDE_ROWS ? lines - SUSAMUNE_GUIDE_ROWS : 0;

	if (first < 0)
		first = 0;
	if (first > last)
		first = last;
	if (delta > last - first)
		return last;
	if (delta < -first)
		return 0;
	return first + delta;
}
