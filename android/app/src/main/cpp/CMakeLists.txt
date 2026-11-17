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

# codigo traduzido: o EU (o que roda) em -O2 por padrao; o JP so precisa existir (-O1, compila mais rapido).
# Os niveis vem do workflow (ee_opt e vu_opt): O1 e o nivel do projeto original, util para ver se uma falha vem do -O2.
set(EE_OPT "$ENV{EE_OPT}")
set(VU_OPT "$ENV{VU_OPT}")
if(NOT EE_OPT)
  set(EE_OPT O2)
endif()
if(NOT VU_OPT)
  set(VU_OPT O2)
endif()
message(STATUS "otimizacao: codigo do jogo -${EE_OPT}, programas VU1 -${VU_OPT}")
file(GLOB GEN_EE "${SS_ROOT}/generated/recomp/*.c")
file(GLOB GEN_VU "${SS_ROOT}/generated/vu/*.c")
file(GLOB GEN_JP "${SS_ROOT}/generated-jp/recomp/*.c")
# runtime, kernel, IOP, GS e HLE
file(GLOB_RECURSE PORT_C "${SS_ROOT}/port/*.c")

# sem protecao de pilha nem FORTIFY (o NDK liga os dois): custam tempo em codigo quente e nao ajudam aqui
set(FAST_OPTS -g0 -fno-strict-aliasing -ffp-contract=off -fno-stack-protector -U_FORTIFY_SOURCE)
include(CheckCCompilerFlag)
check_c_compiler_flag("-mtune=cortex-a73" HAS_MTUNE_A73)
if(HAS_MTUNE_A73)
  list(APPEND FAST_OPTS -mtune=cortex-a73)
endif()

add_library(sstheh SHARED ${GEN_EE} ${GEN_VU} ${GEN_JP} ${PORT_C} android_entry.c)
set_source_files_properties(${GEN_EE} PROPERTIES COMPILE_OPTIONS "-${EE_OPT};-w;${FAST_OPTS}")
set_source_files_properties(${GEN_VU} PROPERTIES COMPILE_OPTIONS "-${VU_OPT};-w;${FAST_OPTS}")
set_source_files_properties(${GEN_JP} PROPERTIES COMPILE_OPTIONS "-O1;-w;${FAST_OPTS}")
set_source_files_properties(${PORT_C} PROPERTIES COMPILE_OPTIONS "-O2;-Wno-unused-parameter;${FAST_OPTS}")
# simbolos visiveis (o profiler precisa dos nomes das funcoes) e -Bsymbolic: as chamadas entre funcoes da
# propria biblioteca continuam diretas, sem passar pela PLT
target_link_options(sstheh PRIVATE -Wl,-Bsymbolic)
# main() do jogo vira ss_main; o SDL_main do Android esta em android_entry.c
set_source_files_properties("${SS_ROOT}/port/main.c" PROPERTIES COMPILE_DEFINITIONS "main=ss_main")
target_include_directories(sstheh PRIVATE
  ${SS_ROOT}/port/runtime ${SS_ROOT}/port/kernel ${SS_ROOT}/port/iop ${SS_ROOT}/port/gs
  ${SS_ROOT}/generated/recomp ${SHDIR})
target_link_libraries(sstheh PRIVATE SDL3::SDL3 m log android dl)
