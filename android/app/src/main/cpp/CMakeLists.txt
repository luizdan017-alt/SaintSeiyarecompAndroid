cmake_minimum_required(VERSION 3.22)
project(sstheh_android C)

# ---- SDL3 compilado junto, como biblioteca compartilhada (libSDL3.so)
set(SDL_SHARED ON CACHE BOOL "" FORCE)
set(SDL_STATIC OFF CACHE BOOL "" FORCE)
set(SDL_TEST_LIBRARY OFF CACHE BOOL "" FORCE)
add_subdirectory(${SDL_DIR} SDL3-build)

# ---- libmain.so: esqueleto (tela azul). Continua sendo o que o app carrega nesta etapa.
add_library(main SHARED skeleton_main.c)
target_link_libraries(main PRIVATE SDL3::SDL3 log)

# ---- libsstheh.so: o motor do Saint Seiya. O app o carrega (GameActivity).
get_filename_component(SS_ROOT "${SS_ROOT}" ABSOLUTE)
message(STATUS "SS_ROOT = ${SS_ROOT}")
if(NOT EXISTS "${SS_ROOT}/port/main.c")
  message(FATAL_ERROR "port/main.c nao encontrado em ${SS_ROOT}")
endif()

# shaders: GLSL -> SPIR-V -> shaders.h (igual ao configure.py)
find_program(GLSLC glslc HINTS "${CMAKE_ANDROID_NDK}/shader-tools/linux-x86_64" "$ENV{ANDROID_NDK_HOME}/shader-tools/linux-x86_64")
if(NOT GLSLC)
  message(FATAL_ERROR "glslc nao encontrado no NDK (${CMAKE_ANDROID_NDK})")
endif()
find_package(Python3 REQUIRED COMPONENTS Interpreter)
set(SHDIR "${CMAKE_BINARY_DIR}/shaders")
file(MAKE_DIRECTORY "${SHDIR}")
file(GLOB SH_VERT "${SS_ROOT}/port/gs/shaders/*.vert")
file(GLOB SH_FRAG "${SS_ROOT}/port/gs/shaders/*.frag")
set(SPVS "")
foreach(sh ${SH_VERT} ${SH_FRAG})
  get_filename_component(shn "${sh}" NAME)
  execute_process(COMMAND "${GLSLC}" -O "${sh}" -o "${SHDIR}/${shn}.spv" RESULT_VARIABLE rc)
  if(NOT rc EQUAL 0)
    message(FATAL_ERROR "glslc falhou em ${sh}")
  endif()
  list(APPEND SPVS "${SHDIR}/${shn}.spv")
endforeach()
execute_process(COMMAND "${Python3_EXECUTABLE}" "${SS_ROOT}/tools/spv2h.py" "${SHDIR}/shaders.h" ${SPVS} RESULT_VARIABLE rc)
if(NOT rc EQUAL 0)
  message(FATAL_ERROR "spv2h.py falhou")
endif()

# codigo traduzido (EU e JP) e programas VU1 embutidos: -O1, sem avisos (e codigo gerado)
file(GLOB GEN_C "${SS_ROOT}/generated/recomp/*.c" "${SS_ROOT}/generated/vu/*.c" "${SS_ROOT}/generated-jp/recomp/*.c")
# runtime, kernel, IOP, GS e HLE
file(GLOB_RECURSE PORT_C "${SS_ROOT}/port/*.c")

add_library(sstheh SHARED ${GEN_C} ${PORT_C} android_entry.c)
set_source_files_properties(${GEN_C} PROPERTIES COMPILE_OPTIONS "-O1;-w;-g0;-fno-strict-aliasing;-ffp-contract=off")
set_source_files_properties(${PORT_C} PROPERTIES COMPILE_OPTIONS "-O2;-g0;-fno-strict-aliasing;-ffp-contract=off;-Wno-unused-parameter")
# main() do jogo vira ss_main; o SDL_main do Android esta em android_entry.c
set_source_files_properties("${SS_ROOT}/port/main.c" PROPERTIES COMPILE_DEFINITIONS "main=ss_main")
target_include_directories(sstheh PRIVATE
  ${SS_ROOT}/port/runtime ${SS_ROOT}/port/kernel ${SS_ROOT}/port/iop ${SS_ROOT}/port/gs
  ${SS_ROOT}/generated/recomp ${SHDIR})
target_link_libraries(sstheh PRIVATE SDL3::SDL3 m log android dl)
target_link_options(sstheh PRIVATE -Wl,--strip-all)
