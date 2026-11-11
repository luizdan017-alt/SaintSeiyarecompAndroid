/* Esqueleto: prova que SDL3 inicia no Android e que o dispositivo grafico (Vulkan) abre.
 * O resultado aparece no logcat (tag "sstheh") e na tela (cor de fundo azul = tudo certo). */
#include <SDL3/SDL.h>
#include <SDL3/SDL_main.h>
#include <android/log.h>

#define LOG(...) __android_log_print(ANDROID_LOG_INFO, "sstheh", __VA_ARGS__)

int main(int argc, char **argv) {
    (void)argc; (void)argv;
    if (!SDL_Init(SDL_INIT_VIDEO | SDL_INIT_AUDIO | SDL_INIT_GAMEPAD)) {
        LOG("SDL_Init falhou: %s", SDL_GetError());
        return 1;
    }
    LOG("SDL %d iniciado", SDL_GetVersion());

    SDL_Window *win = SDL_CreateWindow("sstheh", 0, 0, SDL_WINDOW_FULLSCREEN);
    if (!win) { LOG("janela falhou: %s", SDL_GetError()); return 1; }

    SDL_GPUDevice *dev = SDL_CreateGPUDevice(SDL_GPU_SHADERFORMAT_SPIRV, false, NULL);
    if (dev) {
        LOG("SDL GPU ok, driver: %s", SDL_GetGPUDeviceDriver(dev));
        SDL_ClaimWindowForGPUDevice(dev, win);
    } else {
        LOG("SDL GPU falhou: %s", SDL_GetError());
    }

    for (int run = 1; run;) {
        SDL_Event e;
        while (SDL_PollEvent(&e)) if (e.type == SDL_EVENT_QUIT) run = 0;
        if (dev) {
            SDL_GPUCommandBuffer *cb = SDL_AcquireGPUCommandBuffer(dev);
            SDL_GPUTexture *tex = NULL;
            if (cb && SDL_WaitAndAcquireGPUSwapchainTexture(cb, win, &tex, NULL, NULL) && tex) {
                SDL_GPUColorTargetInfo ct = {0};
                ct.texture = tex;
                ct.clear_color = (SDL_FColor){0.1f, 0.3f, 0.8f, 1.0f};
                ct.load_op = SDL_GPU_LOADOP_CLEAR;
                ct.store_op = SDL_GPU_STOREOP_STORE;
                SDL_GPURenderPass *rp = SDL_BeginGPURenderPass(cb, &ct, 1, NULL);
                SDL_EndGPURenderPass(rp);
            }
            if (cb) SDL_SubmitGPUCommandBuffer(cb);
        } else {
            SDL_Delay(16);
        }
    }
    SDL_Quit();
    return 0;
}
