#include "susamune/ghost_render_feedback.hxx"
#include "susamune/ghost_world_runtime.hxx"
#include "susamune/ghost_trace.hxx"
#include "susamune/addresses.hxx"
#if MOONSHINE_GHOST_TRACE && defined(__powerpc__)
extern "C" unsigned ghostRenderFeedback(unsigned nativeValue,unsigned consumer) {
    const unsigned caller=(consumer==2?MS_FEEDBACK_WATER_SITE:consumer?MS_FEEDBACK_SILHOUETTE_SITE:MS_FEEDBACK_CAMERA_SITE)+4;
    const unsigned seed=*reinterpret_cast<volatile const unsigned*>(SUSAMUNE_ADDR_LIBC_RAND_SEED);
    const unsigned value=consumer==2?GhostWorldRuntime::waterFeedback(caller,nativeValue,seed):
        GhostWorldRuntime::renderFeedback(caller,nativeValue,seed);
    GhostTrace::literalCall(caller,value,seed);
    return value;
}
// Mid-function hooks preserve both FPR lanes, FPSCR and all live integer state.
asm(
    ".set gFeedbackCameraTail," MS_FEEDBACK_CAMERA_TAIL "\n"
    ".set gFeedbackSilhouetteTail," MS_FEEDBACK_SILHOUETTE_TAIL "\n"
    ".pushsection .text.gFeedbackCamera,\"ax\",@progbits\n"
    ".global gFeedbackCamera\n"
    ".type gFeedbackCamera,@function\n"
    "gFeedbackCamera:\n"
    "stwu 1,-672(1)\n"
    "stw 0,104(1)\n"
    "stw 3,64(1)\n"
    "li 3,0\n"
    "b gFeedbackCommon\n"
    ".size gFeedbackCamera,.-gFeedbackCamera\n"
    ".popsection\n"
    ".pushsection .text.gFeedbackSilhouette,\"ax\",@progbits\n"
    ".global gFeedbackSilhouette\n"
    ".type gFeedbackSilhouette,@function\n"
    "gFeedbackSilhouette:\n"
    "stwu 1,-672(1)\n"
    "stw 0,104(1)\n"
    "stw 3,64(1)\n"
    "li 3,1\n"
    "b gFeedbackCommon\n"
    ".size gFeedbackSilhouette,.-gFeedbackSilhouette\n"
    ".popsection\n"
    ".pushsection .text.gFeedbackWater,\"ax\",@progbits\n"
    ".global gFeedbackWater\n"
    ".type gFeedbackWater,@function\n"
    "gFeedbackWater:\n"
    "stwu 1,-672(1)\n"
    "stw 0,104(1)\n"
    "stw 3,64(1)\n"
    "li 3,2\n"
    "b gFeedbackCommon\n"
    ".size gFeedbackWater,.-gFeedbackWater\n"
    ".popsection\n"
    ".pushsection .text.gFeedbackCommon,\"ax\",@progbits\n"
    ".global gFeedbackCommon\n"
    ".type gFeedbackCommon,@function\n"
    "gFeedbackCommon:\n"
    "stw 3,136(1)\n"
    "stw 4,68(1)\n"
    "stw 5,72(1)\n"
    "stw 6,76(1)\n"
    "stw 7,80(1)\n"
    "stw 8,84(1)\n"
    "stw 9,88(1)\n"
    "stw 10,92(1)\n"
    "stw 11,96(1)\n"
    "stw 12,100(1)\n"
    "mfcr 0\n"
    "stw 0,108(1)\n"
    "mflr 0\n"
    "stw 0,112(1)\n"
    "mfctr 0\n"
    "stw 0,116(1)\n"
    "mfxer 0\n"
    "stw 0,120(1)\n"
    "stfd 0,144(1)\n"
    "stfd 1,152(1)\n"
    "stfd 2,160(1)\n"
    "stfd 3,168(1)\n"
    "stfd 4,176(1)\n"
    "stfd 5,184(1)\n"
    "stfd 6,192(1)\n"
    "stfd 7,200(1)\n"
    "stfd 8,208(1)\n"
    "stfd 9,216(1)\n"
    "stfd 10,224(1)\n"
    "stfd 11,232(1)\n"
    "stfd 12,240(1)\n"
    "stfd 13,248(1)\n"
    "stfd 14,256(1)\n"
    "stfd 15,264(1)\n"
    "stfd 16,272(1)\n"
    "stfd 17,280(1)\n"
    "stfd 18,288(1)\n"
    "stfd 19,296(1)\n"
    "stfd 20,304(1)\n"
    "stfd 21,312(1)\n"
    "stfd 22,320(1)\n"
    "stfd 23,328(1)\n"
    "stfd 24,336(1)\n"
    "stfd 25,344(1)\n"
    "stfd 26,352(1)\n"
    "stfd 27,360(1)\n"
    "stfd 28,368(1)\n"
    "stfd 29,376(1)\n"
    "stfd 30,384(1)\n"
    "stfd 31,392(1)\n"
    ".long 0x100004e0\n" // ps_merge11 0,0,0
    "stfd 0,400(1)\n"
    ".long 0x10010ce0\n" // ps_merge11 0,1,1
    "stfd 0,408(1)\n"
    ".long 0x100214e0\n" // ps_merge11 0,2,2
    "stfd 0,416(1)\n"
    ".long 0x10031ce0\n" // ps_merge11 0,3,3
    "stfd 0,424(1)\n"
    ".long 0x100424e0\n" // ps_merge11 0,4,4
    "stfd 0,432(1)\n"
    ".long 0x10052ce0\n" // ps_merge11 0,5,5
    "stfd 0,440(1)\n"
    ".long 0x100634e0\n" // ps_merge11 0,6,6
    "stfd 0,448(1)\n"
    ".long 0x10073ce0\n" // ps_merge11 0,7,7
    "stfd 0,456(1)\n"
    ".long 0x100844e0\n" // ps_merge11 0,8,8
    "stfd 0,464(1)\n"
    ".long 0x10094ce0\n" // ps_merge11 0,9,9
    "stfd 0,472(1)\n"
    ".long 0x100a54e0\n" // ps_merge11 0,10,10
    "stfd 0,480(1)\n"
    ".long 0x100b5ce0\n" // ps_merge11 0,11,11
    "stfd 0,488(1)\n"
    ".long 0x100c64e0\n" // ps_merge11 0,12,12
    "stfd 0,496(1)\n"
    ".long 0x100d6ce0\n" // ps_merge11 0,13,13
    "stfd 0,504(1)\n"
    ".long 0x100e74e0\n" // ps_merge11 0,14,14
    "stfd 0,512(1)\n"
    ".long 0x100f7ce0\n" // ps_merge11 0,15,15
    "stfd 0,520(1)\n"
    ".long 0x101084e0\n" // ps_merge11 0,16,16
    "stfd 0,528(1)\n"
    ".long 0x10118ce0\n" // ps_merge11 0,17,17
    "stfd 0,536(1)\n"
    ".long 0x101294e0\n" // ps_merge11 0,18,18
    "stfd 0,544(1)\n"
    ".long 0x10139ce0\n" // ps_merge11 0,19,19
    "stfd 0,552(1)\n"
    ".long 0x1014a4e0\n" // ps_merge11 0,20,20
    "stfd 0,560(1)\n"
    ".long 0x1015ace0\n" // ps_merge11 0,21,21
    "stfd 0,568(1)\n"
    ".long 0x1016b4e0\n" // ps_merge11 0,22,22
    "stfd 0,576(1)\n"
    ".long 0x1017bce0\n" // ps_merge11 0,23,23
    "stfd 0,584(1)\n"
    ".long 0x1018c4e0\n" // ps_merge11 0,24,24
    "stfd 0,592(1)\n"
    ".long 0x1019cce0\n" // ps_merge11 0,25,25
    "stfd 0,600(1)\n"
    ".long 0x101ad4e0\n" // ps_merge11 0,26,26
    "stfd 0,608(1)\n"
    ".long 0x101bdce0\n" // ps_merge11 0,27,27
    "stfd 0,616(1)\n"
    ".long 0x101ce4e0\n" // ps_merge11 0,28,28
    "stfd 0,624(1)\n"
    ".long 0x101dece0\n" // ps_merge11 0,29,29
    "stfd 0,632(1)\n"
    ".long 0x101ef4e0\n" // ps_merge11 0,30,30
    "stfd 0,640(1)\n"
    ".long 0x101ffce0\n" // ps_merge11 0,31,31
    "stfd 0,648(1)\n"
    "mffs 0\n"
    "stfd 0,128(1)\n"
    "lwz 4,136(1)\n"
    "cmpwi 4,2\n"
    "bne .Lgf_integer_value\n"
    "stfs 1,656(1)\n"
    "lwz 3,656(1)\n"
    "b .Lgf_value_ready\n"
    ".Lgf_integer_value:\n"
    "lwz 3,104(1)\n"
    ".Lgf_value_ready:\n"
    "bl ghostRenderFeedback\n"
    "lwz 4,136(1)\n"
    "cmpwi 4,2\n"
    "bne .Lgf_integer_result\n"
    "lwz 4,656(1)\n"
    "cmplw 3,4\n"
    "beq .Lgf_result_ready\n"
    "stw 3,656(1)\n"
    "lfs 1,656(1)\n"
    "stfd 1,152(1)\n"
    "b .Lgf_result_ready\n"
    ".Lgf_integer_result:\n"
    "stw 3,104(1)\n"
    ".Lgf_result_ready:\n"
    "lfd 0,400(1)\n"
    ".long 0x10000420\n" // ps_merge00 0,0,0
    "lfd 0,408(1)\n"
    ".long 0x10210420\n" // ps_merge00 1,1,0
    "lfd 0,416(1)\n"
    ".long 0x10420420\n" // ps_merge00 2,2,0
    "lfd 0,424(1)\n"
    ".long 0x10630420\n" // ps_merge00 3,3,0
    "lfd 0,432(1)\n"
    ".long 0x10840420\n" // ps_merge00 4,4,0
    "lfd 0,440(1)\n"
    ".long 0x10a50420\n" // ps_merge00 5,5,0
    "lfd 0,448(1)\n"
    ".long 0x10c60420\n" // ps_merge00 6,6,0
    "lfd 0,456(1)\n"
    ".long 0x10e70420\n" // ps_merge00 7,7,0
    "lfd 0,464(1)\n"
    ".long 0x11080420\n" // ps_merge00 8,8,0
    "lfd 0,472(1)\n"
    ".long 0x11290420\n" // ps_merge00 9,9,0
    "lfd 0,480(1)\n"
    ".long 0x114a0420\n" // ps_merge00 10,10,0
    "lfd 0,488(1)\n"
    ".long 0x116b0420\n" // ps_merge00 11,11,0
    "lfd 0,496(1)\n"
    ".long 0x118c0420\n" // ps_merge00 12,12,0
    "lfd 0,504(1)\n"
    ".long 0x11ad0420\n" // ps_merge00 13,13,0
    "lfd 0,512(1)\n"
    ".long 0x11ce0420\n" // ps_merge00 14,14,0
    "lfd 0,520(1)\n"
    ".long 0x11ef0420\n" // ps_merge00 15,15,0
    "lfd 0,528(1)\n"
    ".long 0x12100420\n" // ps_merge00 16,16,0
    "lfd 0,536(1)\n"
    ".long 0x12310420\n" // ps_merge00 17,17,0
    "lfd 0,544(1)\n"
    ".long 0x12520420\n" // ps_merge00 18,18,0
    "lfd 0,552(1)\n"
    ".long 0x12730420\n" // ps_merge00 19,19,0
    "lfd 0,560(1)\n"
    ".long 0x12940420\n" // ps_merge00 20,20,0
    "lfd 0,568(1)\n"
    ".long 0x12b50420\n" // ps_merge00 21,21,0
    "lfd 0,576(1)\n"
    ".long 0x12d60420\n" // ps_merge00 22,22,0
    "lfd 0,584(1)\n"
    ".long 0x12f70420\n" // ps_merge00 23,23,0
    "lfd 0,592(1)\n"
    ".long 0x13180420\n" // ps_merge00 24,24,0
    "lfd 0,600(1)\n"
    ".long 0x13390420\n" // ps_merge00 25,25,0
    "lfd 0,608(1)\n"
    ".long 0x135a0420\n" // ps_merge00 26,26,0
    "lfd 0,616(1)\n"
    ".long 0x137b0420\n" // ps_merge00 27,27,0
    "lfd 0,624(1)\n"
    ".long 0x139c0420\n" // ps_merge00 28,28,0
    "lfd 0,632(1)\n"
    ".long 0x13bd0420\n" // ps_merge00 29,29,0
    "lfd 0,640(1)\n"
    ".long 0x13de0420\n" // ps_merge00 30,30,0
    "lfd 0,648(1)\n"
    ".long 0x13ff0420\n" // ps_merge00 31,31,0
    "lfd 1,152(1)\n"
    "lfd 2,160(1)\n"
    "lfd 3,168(1)\n"
    "lfd 4,176(1)\n"
    "lfd 5,184(1)\n"
    "lfd 6,192(1)\n"
    "lfd 7,200(1)\n"
    "lfd 8,208(1)\n"
    "lfd 9,216(1)\n"
    "lfd 10,224(1)\n"
    "lfd 11,232(1)\n"
    "lfd 12,240(1)\n"
    "lfd 13,248(1)\n"
    "lfd 14,256(1)\n"
    "lfd 15,264(1)\n"
    "lfd 16,272(1)\n"
    "lfd 17,280(1)\n"
    "lfd 18,288(1)\n"
    "lfd 19,296(1)\n"
    "lfd 20,304(1)\n"
    "lfd 21,312(1)\n"
    "lfd 22,320(1)\n"
    "lfd 23,328(1)\n"
    "lfd 24,336(1)\n"
    "lfd 25,344(1)\n"
    "lfd 26,352(1)\n"
    "lfd 27,360(1)\n"
    "lfd 28,368(1)\n"
    "lfd 29,376(1)\n"
    "lfd 30,384(1)\n"
    "lfd 31,392(1)\n"
    "lfd 0,128(1)\n"
    "mtfsf 255,0\n"
    "lfd 0,144(1)\n"
    "lwz 0,112(1)\n"
    "mtlr 0\n"
    "lwz 0,116(1)\n"
    "mtctr 0\n"
    "lwz 0,120(1)\n"
    "mtxer 0\n"
    "lwz 3,64(1)\n"
    "lwz 4,68(1)\n"
    "lwz 5,72(1)\n"
    "lwz 6,76(1)\n"
    "lwz 7,80(1)\n"
    "lwz 8,84(1)\n"
    "lwz 9,88(1)\n"
    "lwz 10,92(1)\n"
    "lwz 11,96(1)\n"
    "lwz 12,100(1)\n"
    "lwz 0,136(1)\n"
    "cmpwi 0,2\n"
    "beq .Lgf_water_tail\n"
    "cmpwi 0,0\n"
    "bne 1f\n"
    "lwz 0,108(1)\n"
    "mtcrf 255,0\n"
    "lwz 0,104(1)\n"
    "addi 1,1,672\n"
    "clrlwi. 0,0,24\n"
    "b ctrlNormalOrTowerCamera___15CPolarSubCameraFv+0x3c4\n"
    "1:\n"
    "lwz 0,108(1)\n"
    "mtcrf 255,0\n"
    "lwz 0,104(1)\n"
    "addi 1,1,672\n"
    "clrlwi. 0,0,24\n"
    "b perform__11TSilhouetteFUlPQ26JDrama9TGraphics+0x4c\n"
    ".Lgf_water_tail:\n"
    "lwz 0,108(1)\n"
    "mtcrf 255,0\n"
    "lwz 0,104(1)\n"
    "addi 1,1,672\n"
    "lwz 0,12(1)\n"
    "b getWaterHeight__17TBathWaterManagerCFff+0x40\n"
    ".size gFeedbackCommon,.-gFeedbackCommon\n"
    ".popsection\n"
);
#endif
