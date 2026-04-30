# Azul Plugin JADX

Decompiles Android APK/DEX files using [JADX](https://github.com/skylot/jadx).

## Installation

### Installing Java locally (required to run JADX)

```
sudo apt install default-jre
```

### Installing JADX

JADX is the Android decompiler used by this plugin.
https://github.com/skylot/jadx


```bash
# Download JADX, make it executable, and put it on PATH
sudo scripts/install_jadx.sh
```


### Development Installation 

To install azul-plugin-jadx for development run the command (from the root directory of this project):
```
uv sync
```

Then enter the virtual environment:
```
source .venv/bin/activate
```

## Usage

Usage on local files:

```
$ azul-plugin-jadx malware.apk
level=INFO time=2026-04-01 12:00:00+0000 name=azul_runner.plugin custom startup options:
level=INFO time=2026-04-01 12:00:00+0000 name=azul_runner.plugin max_file_size       : 104857600
level=INFO time=2026-04-01 12:00:00+0000 name=azul_runner.coordinator received plugin=AzulPluginJadx type=Android APK size=1234567 id=abc123...
level=INFO time=2026-04-01 12:00:05+0000 name=azul_plugin_jadx Successfully analyzed 116 source files.
level=INFO time=2026-04-01 12:00:05+0000 name=azul_runner.coordinator finish plugin=AzulPluginJadx mp=None state=OK type=Android APK size=1234567 id=abc123...
level=INFO time=2026-04-01 12:00:05+0000 name=azul_runner.main Processing complete
----- AzulPluginJadx results -----
OK

events (1)

event for binary:abc123...:None
  {}
  output data streams (116):
    ... decompiled .java files ...
  output features:
              package_name: ctsoft.androidapps.calltimer
              version_code: 2103198
              version_name: 2.0.98R
           min_sdk_version: 30
        target_sdk_version: 35
       compile_sdk_version: 34
               permissions: android.permission.SYSTEM_ALERT_WINDOW
                            android.permission.READ_PHONE_STATE
                            android.permission.CALL_PHONE
                            ...
             features_used: android.hardware.telephony
                activities: ctsoft.androidapps.calltimer.SettingsActivity
                            ctsoft.androidapps.calltimer.DisplayOverlayActivity
                            ...
                  services: ctsoft.androidapps.calltimer.OverlayDisplayingService
                            ctsoft.androidapps.calltimer.ScreeningService
                            ...
                 receivers: ctsoft.androidapps.calltimer.IncomingReceiver
                            ctsoft.androidapps.calltimer.BootReceiver
                            ...
   package_class_methods: ctsoft.androidapps.calltimer.CrossCallSettings::onCreate
                          ctsoft.androidapps.calltimer.CrossCallSettings::onResume
                          ...
         class_methods: CrossCallSettings::onCreate
                        CrossCallSettings::onResume
                        ...
       package_methods: ctsoft.androidapps.calltimer::onCreate
                        ...
               classes: CrossCallSettings
                        CallTimerApp
                        ...
      package_classes: ctsoft.androidapps.calltimer.CrossCallSettings
                       ctsoft.androidapps.calltimer.CallTimerApp
                       ...
              packages: ctsoft
                        ctsoft.androidapps
                        ctsoft.androidapps.calltimer
                        ...
                 enums: ...
            interfaces: ...

Feature key:
  package_name:  The Android package name from AndroidManifest.xml.
  version_code:  The versionCode from AndroidManifest.xml.
  version_name:  The versionName from AndroidManifest.xml.
  min_sdk_version:  The minSdkVersion from AndroidManifest.xml.
  target_sdk_version:  The targetSdkVersion from AndroidManifest.xml.
  compile_sdk_version:  The compileSdkVersion from AndroidManifest.xml.
  permissions:  Android permissions declared in AndroidManifest.xml.
  features_used:  Hardware/software features declared via <uses-feature> in AndroidManifest.xml.
  activities:  User-defined Activity class names declared in AndroidManifest.xml.
  services:  User-defined Service class names declared in AndroidManifest.xml.
  receivers:  User-defined BroadcastReceiver class names declared in AndroidManifest.xml.
  providers:  User-defined ContentProvider class names declared in AndroidManifest.xml.
  package_class_methods:  Fully-pathed methods in user-package source: com.example.MyClass::method.
  class_methods:  Class-level methods in user-package source: MyClass::method.
  package_methods:  Package-level methods in user-package source: com.example::method.
  classes:  All class names found in user-package source.
  package_classes:  Fully-qualified class names found in user-package source.
  packages:  All package levels found in user-package source.
  enums:  All enum type names found in user-package source.
  interfaces:  All interface type names found in user-package source.
```

Check `azul-plugin-jadx --help` for advanced usage.

## Python Package management

This python package is managed using a `pyproject.toml` file.

Standardisation of installing and testing the python package is handled through tox.
Tox commands include:

```bash
# Run all standard tox actions
tox
# Run linting only
tox -e style
# Run tests only
tox -e test
```

## Dependency management

Dependencies are managed in the pyproject.toml and debian.txt file.

Version pinning is achieved using the `uv.lock` file.

To add new dependencies it's recommended to use uv with the command `uv add <new-package>`
    or for a dev package `uv add --dev <new-dev-package>`

The tool used for linting and managing styling is `ruff` and it is configured via `pyproject.toml`

The debian.txt file manages the debian dependencies that need to be installed on development systems and docker images.

Sometimes the debian.txt file is insufficient and in this case the Dockerfile may need to be modified directly to
install complex dependencies.
