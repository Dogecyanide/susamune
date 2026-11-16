#include <string.h>
void *memcpy(void *out,const void *in,size_t n){unsigned char *d=out;const unsigned char *s=in;while(n--)*d++=*s++;return out;}
void *memmove(void *out,const void *in,size_t n){unsigned char *d=out;const unsigned char *s=in;if(d>s && d<s+n){d+=n;s+=n;while(n--)*--d=*--s;}else while(n--)*d++=*s++;return out;}
void *memset(void *out,int v,size_t n){unsigned char *d=out;while(n--)*d++=(unsigned char)v;return out;}
int memcmp(const void *a,const void *b,size_t n){const unsigned char *x=a,*y=b;while(n--){if(*x!=*y)return (int)*x-*y;++x;++y;}return 0;}
size_t strlen(const char *s){const char *p=s;while(*p)++p;return p-s;}
char *strcpy(char *d,const char *s){char *out=d;while((*d++=*s++));return out;}
char *strcat(char *d,const char *s){strcpy(d+strlen(d),s);return d;}
int strcmp(const char *a,const char *b){while(*a && *a==*b){++a;++b;}return (unsigned char)*a-(unsigned char)*b;}
int strncmp(const char *a,const char *b,size_t n){while(n--){if(*a!=*b || !*a)return (unsigned char)*a-(unsigned char)*b;++a;++b;}return 0;}
char *strchr(const char *s,int c){while(*s && *s!=(char)c)++s;return *s==(char)c?(char *)s:NULL;}

void *memchr(const void *data,int value,size_t n){const unsigned char *p=data;while(n--){if(*p==(unsigned char)value)return (void *)p;++p;}return NULL;}
