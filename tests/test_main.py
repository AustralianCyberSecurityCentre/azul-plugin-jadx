"""Tests for AzulPluginJadx."""

from azul_runner import FV, DataLabel, JobResult, State, test_template

from azul_plugin_jadx.main import AzulPluginJadx


class TestExecute(test_template.TestPlugin):
    """Tests for AzulPluginJadx.execute()."""

    PLUGIN_TO_TEST = AzulPluginJadx

    def test_bad_file_type(self):
        """A non-APK/DEX file should be opted out."""
        data = self.load_test_file_bytes(
            "702e31ed1537c279459a255460f12f0f2863f973e121cd9194957f4f3e7b0994",
            "Benign WIN32 EXE, python library executable python_mcp.exe",
        )
        result = self.do_execution(
            data_in=[("content", data)],
            verify_input_content=False,
        )
        self.assertJobResult(
            result,
            JobResult(state=State(State.Label.OPT_OUT, message="Not a valid APK/DEX file.")),
        )

    def test_apk_calculator(self):
        """A real APK should decompile successfully with manifest features and source files."""
        data = self.load_test_file_bytes(
            "dc7216ea61174f801b7fff99b9a3e0ac669080ead1e51243dbebb0bae6839bcf",
            "Cute Calc 4.0.0 APK (com.sosauce.cutecalc) from F-Droid.",
        )
        result = self.do_execution(
            data_in=[("content", data)],
            verify_input_content=False,
        )
        self.assertEqual(result.state, State(State.Label.COMPLETED))

        self.assertEqual(len(result.events), 1)
        event = result.events[0]

        # --- Decompiled source files ---
        self.assertEqual(len(event.data), 1)
        self.assertTrue(all(d.label == DataLabel.DECOMPILED_JAVA for d in event.data))

        # --- All features ---
        self.assertReprEqual(
            event.features,
            {
                "classes": [
                    FV("R"),
                    FV("attr"),
                    FV("color"),
                    FV("dimen"),
                    FV("drawable"),
                    FV("font"),
                    FV("id"),
                    FV("integer"),
                    FV("layout"),
                    FV("mipmap"),
                    FV("string"),
                    FV("style"),
                ],
                "compile_sdk_version": [
                    FV("36"),
                ],
                "min_sdk_version": [
                    FV("23"),
                ],
                "package_classes": [
                    FV("com.sosauce.cutecalc.R"),
                    FV("com.sosauce.cutecalc.attr"),
                    FV("com.sosauce.cutecalc.color"),
                    FV("com.sosauce.cutecalc.dimen"),
                    FV("com.sosauce.cutecalc.drawable"),
                    FV("com.sosauce.cutecalc.font"),
                    FV("com.sosauce.cutecalc.id"),
                    FV("com.sosauce.cutecalc.integer"),
                    FV("com.sosauce.cutecalc.layout"),
                    FV("com.sosauce.cutecalc.mipmap"),
                    FV("com.sosauce.cutecalc.string"),
                    FV("com.sosauce.cutecalc.style"),
                ],
                "package_name": [
                    FV("com.sosauce.cutecalc"),
                ],
                "packages": [
                    FV("com"),
                    FV("com.sosauce"),
                    FV("com.sosauce.cutecalc"),
                ],
                "permissions": [
                    FV("android.permission.MEDIA_CONTENT_CONTROL"),
                    FV("android.permission.VIBRATE"),
                    FV("com.sosauce.cutecalc.DYNAMIC_RECEIVER_NOT_EXPORTED_PERMISSION"),
                ],
                "target_sdk_version": [
                    FV("36"),
                ],
                "version_code": [
                    FV("50000"),
                ],
                "version_name": [
                    FV("4.0.0"),
                ],
            },
        )

    def test_apk_cpustress(self):
        """A real APK should decompile successfully with manifest features and source files."""
        data = self.load_test_file_bytes(
            "1675c91546799a3fdad7b0ba09bd1d600a41daa2f3fef18f2bea96e99e883205",
            "Simpre CPU Stress test tool for Android 1.4.0 from F-Droid (com.simpre.cpustress).",
        )
        result = self.do_execution(
            data_in=[("content", data)],
            verify_input_content=False,
        )
        self.assertEqual(result.state, State(State.Label.COMPLETED))

        self.assertEqual(len(result.events), 1)
        event = result.events[0]

        # --- Decompiled source files ---
        self.assertEqual(len(event.data), 5)
        self.assertTrue(all(d.label == DataLabel.DECOMPILED_JAVA for d in event.data))

        # --- All features ---
        self.assertReprEqual(
            event.features,
            {
                "activities": [
                    FV("net.tlfoxhuman.droidstress.AboutActivity"),
                    FV("net.tlfoxhuman.droidstress.BlankScreenActivity"),
                    FV("net.tlfoxhuman.droidstress.MainActivity"),
                ],
                "class_methods": [
                    FV("AboutActivity::onCreate"),
                    FV("AboutActivity::setContentView"),
                    FV("BlankScreenActivity::getWindow"),
                    FV("BlankScreenActivity::onCreate"),
                    FV("BlankScreenActivity::onDestroy"),
                    FV("BlankScreenActivity::onSystemUiVisibilityChange"),
                    FV("BlankScreenActivity::setContentView"),
                    FV("MainActivity::MainActivity"),
                    FV("MainActivity::getMenuInflater"),
                    FV("MainActivity::getWindow"),
                    FV("MainActivity::onClick"),
                    FV("MainActivity::onCreate"),
                    FV("MainActivity::onCreateOptionsMenu"),
                    FV("MainActivity::onDestroy"),
                    FV("MainActivity::onOptionsItemSelected"),
                    FV("MainActivity::setContentView"),
                    FV("MainActivity::startActivity"),
                    FV("MainActivity::startService"),
                    FV("StressService::onBind"),
                    FV("StressService::onDestroy"),
                    FV("StressService::onStartCommand"),
                ],
                "classes": [
                    FV("AboutActivity"),
                    FV("BlankScreenActivity"),
                    FV("MainActivity"),
                    FV("R"),
                    FV("StressService"),
                    FV("anim"),
                    FV("attr"),
                    FV("bool"),
                    FV("color"),
                    FV("dimen"),
                    FV("drawable"),
                    FV("id"),
                    FV("integer"),
                    FV("interpolator"),
                    FV("layout"),
                    FV("menu"),
                    FV("mipmap"),
                    FV("string"),
                    FV("style"),
                    FV("xml"),
                ],
                "compile_sdk_version": [
                    FV("36"),
                ],
                "min_sdk_version": [
                    FV("16"),
                ],
                "package_class_methods": [
                    FV("net.tlfoxhuman.droidstress.AboutActivity::onCreate"),
                    FV("net.tlfoxhuman.droidstress.AboutActivity::setContentView"),
                    FV("net.tlfoxhuman.droidstress.BlankScreenActivity::getWindow"),
                    FV("net.tlfoxhuman.droidstress.BlankScreenActivity::onCreate"),
                    FV("net.tlfoxhuman.droidstress.BlankScreenActivity::onDestroy"),
                    FV("net.tlfoxhuman.droidstress.BlankScreenActivity::onSystemUiVisibilityChange"),
                    FV("net.tlfoxhuman.droidstress.BlankScreenActivity::setContentView"),
                    FV("net.tlfoxhuman.droidstress.MainActivity::MainActivity"),
                    FV("net.tlfoxhuman.droidstress.MainActivity::getMenuInflater"),
                    FV("net.tlfoxhuman.droidstress.MainActivity::getWindow"),
                    FV("net.tlfoxhuman.droidstress.MainActivity::onClick"),
                    FV("net.tlfoxhuman.droidstress.MainActivity::onCreate"),
                    FV("net.tlfoxhuman.droidstress.MainActivity::onCreateOptionsMenu"),
                    FV("net.tlfoxhuman.droidstress.MainActivity::onDestroy"),
                    FV("net.tlfoxhuman.droidstress.MainActivity::onOptionsItemSelected"),
                    FV("net.tlfoxhuman.droidstress.MainActivity::setContentView"),
                    FV("net.tlfoxhuman.droidstress.MainActivity::startActivity"),
                    FV("net.tlfoxhuman.droidstress.MainActivity::startService"),
                    FV("net.tlfoxhuman.droidstress.StressService::onBind"),
                    FV("net.tlfoxhuman.droidstress.StressService::onDestroy"),
                    FV("net.tlfoxhuman.droidstress.StressService::onStartCommand"),
                ],
                "package_classes": [
                    FV("net.tlfoxhuman.droidstress.AboutActivity"),
                    FV("net.tlfoxhuman.droidstress.BlankScreenActivity"),
                    FV("net.tlfoxhuman.droidstress.MainActivity"),
                    FV("net.tlfoxhuman.droidstress.R"),
                    FV("net.tlfoxhuman.droidstress.StressService"),
                    FV("net.tlfoxhuman.droidstress.anim"),
                    FV("net.tlfoxhuman.droidstress.attr"),
                    FV("net.tlfoxhuman.droidstress.bool"),
                    FV("net.tlfoxhuman.droidstress.color"),
                    FV("net.tlfoxhuman.droidstress.dimen"),
                    FV("net.tlfoxhuman.droidstress.drawable"),
                    FV("net.tlfoxhuman.droidstress.id"),
                    FV("net.tlfoxhuman.droidstress.integer"),
                    FV("net.tlfoxhuman.droidstress.interpolator"),
                    FV("net.tlfoxhuman.droidstress.layout"),
                    FV("net.tlfoxhuman.droidstress.menu"),
                    FV("net.tlfoxhuman.droidstress.mipmap"),
                    FV("net.tlfoxhuman.droidstress.string"),
                    FV("net.tlfoxhuman.droidstress.style"),
                    FV("net.tlfoxhuman.droidstress.xml"),
                ],
                "package_methods": [
                    FV("net.tlfoxhuman.droidstress::MainActivity"),
                    FV("net.tlfoxhuman.droidstress::getMenuInflater"),
                    FV("net.tlfoxhuman.droidstress::getWindow"),
                    FV("net.tlfoxhuman.droidstress::onBind"),
                    FV("net.tlfoxhuman.droidstress::onClick"),
                    FV("net.tlfoxhuman.droidstress::onCreate"),
                    FV("net.tlfoxhuman.droidstress::onCreateOptionsMenu"),
                    FV("net.tlfoxhuman.droidstress::onDestroy"),
                    FV("net.tlfoxhuman.droidstress::onOptionsItemSelected"),
                    FV("net.tlfoxhuman.droidstress::onStartCommand"),
                    FV("net.tlfoxhuman.droidstress::onSystemUiVisibilityChange"),
                    FV("net.tlfoxhuman.droidstress::setContentView"),
                    FV("net.tlfoxhuman.droidstress::startActivity"),
                    FV("net.tlfoxhuman.droidstress::startService"),
                ],
                "package_name": [
                    FV("net.tlfoxhuman.droidstress"),
                ],
                "packages": [
                    FV("net"),
                    FV("net.tlfoxhuman"),
                    FV("net.tlfoxhuman.droidstress"),
                ],
                "permissions": [
                    FV("android.permission.FOREGROUND_SERVICE"),
                    FV("android.permission.FOREGROUND_SERVICE_SPECIAL_USE"),
                    FV("android.permission.POST_NOTIFICATIONS"),
                    FV("android.permission.WAKE_LOCK"),
                    FV("net.tlfoxhuman.droidstress.DYNAMIC_RECEIVER_NOT_EXPORTED_PERMISSION"),
                ],
                "services": [
                    FV("net.tlfoxhuman.droidstress.StressService"),
                ],
                "target_sdk_version": [
                    FV("36"),
                ],
                "version_code": [
                    FV("5"),
                ],
                "version_name": [
                    FV("1.4.0"),
                ],
            },
        )
