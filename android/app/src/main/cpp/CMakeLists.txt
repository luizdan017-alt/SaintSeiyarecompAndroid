cmake_minimum_required(VERSION 3.22)
project(sstheh_android C)

# SDL3 compilado junto, como biblioteca compartilhada (libSDL3.so)
set(SDL_SHARED ON CACHE BOOL "" FORCE)
set(SDL_STATIC OFF CACHE BOOL "" FORCE)
set(SDL_TEST_LIBRARY OFF CACHE BOOL "" FORCE)
add_subdirectory(${SDL_DIR} SDL3-build)

# libmain.so: o ponto de entrada (SDL_main). Na Etapa 3 ele passa a conter o motor.
add_library(main SHARED skeleton_main.c)
target_link_libraries(main PRIVATE SDL3::SDL3 log)
