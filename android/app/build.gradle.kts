plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
    id("com.chaquo.python")
}

// The shared HYPOLAB code lives at the repository root; it is copied (never edited) into the build.
val repoRoot = rootProject.projectDir.parentFile
val hypolabSrc = layout.buildDirectory.dir("hypolab-src")
val syncHypolab by tasks.registering(Sync::class) {
    from(repoRoot) {
        include("hypolab/**", "ideaengine/**", "ideaweb/**", "data/**")
        exclude("**/__pycache__/**", "**/*.pyc")
    }
    into(hypolabSrc)
}

// Permanent signing key: only from GitHub secrets (never committed). Without them the build is
// signed with a throwaway debug key, fine for the spike but not for updates that keep your data.
val storePw: String? = System.getenv("HYPOLAB_STORE_PASSWORD")
val storeFileEnv: String? = System.getenv("HYPOLAB_KEYSTORE")
val hasReleaseKey = !storePw.isNullOrBlank() && storeFileEnv != null && file(storeFileEnv).exists()

android {
    namespace = "ke.zacc.hypolab"
    compileSdk = 35

    defaultConfig {
        applicationId = "ke.zacc.hypolab"
        minSdk = 26
        targetSdk = 35
        versionCode = 8
        versionName = "1.17.0"
        ndk { abiFilters += listOf("arm64-v8a", "x86_64") }
    }

    signingConfigs {
        if (hasReleaseKey) create("release") {
            storeFile = file(storeFileEnv!!)
            storePassword = storePw
            keyAlias = "hypolab"
            keyPassword = storePw
        }
    }
    buildTypes {
        release {
            isMinifyEnabled = false
            signingConfig = signingConfigs.getByName(if (hasReleaseKey) "release" else "debug")
        }
    }
    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    kotlinOptions { jvmTarget = "17" }
}

dependencies {
    // 1.17.0: BRAIN's face-scan page (and any outside link) opens in a Custom Tab inside HYPOLAB
    implementation("androidx.browser:browser:1.8.0")
}

chaquopy {
    defaultConfig {
        version = "3.11"
        pip {
            // chaquo.com (the Android wheels) is sometimes slow from GitHub's runners: wait and retry longer
            options("--timeout", "90")
            options("--retries", "10")
            // Pinned to Chaquopy's prebuilt Android wheels (the ones that ran on the tablet in phases A-B).
            // Unpinned, pip picked numpy 2.4.6 from source on 22 Oct, which cannot be compiled for Android.
            install("numpy==1.26.2")
            install("pandas==2.1.3")
            install("pyyaml")
            install("requests")
            install("matplotlib")
            install("starlette")
            install("uvicorn")
            install("jinja2")
            install("markdown")
            install("python-multipart")
        }
        // engine files read their bundled data by path, so keep them as real files on disk
        extractPackages += listOf("hypolab", "ideaengine", "ideaweb")
    }
    sourceSets {
        getByName("main") {
            srcDir("src/main/python")
            srcDir(hypolabSrc)
        }
    }
}

tasks.named("preBuild") { dependsOn(syncHypolab) }
// Chaquopy's merge task must also see the copied code
tasks.configureEach { if (name.startsWith("merge") && name.contains("PythonSources")) dependsOn(syncHypolab) }
