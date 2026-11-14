plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
}

android {
    namespace = "com.luizdan.sstheh"
    compileSdk = 34

    defaultConfig {
        applicationId = "com.luizdan.sstheh"
        minSdk = 29
        targetSdk = 34
        versionCode = 1
        versionName = "0.0.1-esqueleto"
        ndk { abiFilters += listOf("arm64-v8a") }
        externalNativeBuild {
            cmake {
                arguments += listOf(
                    "-DANDROID_STL=c++_shared",
                    "-DSDL_DIR=${rootProject.projectDir}/third_party/SDL",
                    "-DSS_ROOT=${rootProject.projectDir}/..",
                    "-DCMAKE_BUILD_TYPE=Release"
                )
            }
        }
    }

    externalNativeBuild {
        cmake {
            path = file("src/main/cpp/CMakeLists.txt")
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    kotlinOptions { jvmTarget = "17" }

    packaging {
        jniLibs {
            useLegacyPackaging = true                    // a biblioteca e extraida como arquivo (o profiler le os simbolos dela)
            keepDebugSymbols += "**/libsstheh.so"
        }
    }
}
