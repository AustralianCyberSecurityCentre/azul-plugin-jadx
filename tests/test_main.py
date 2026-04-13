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
        # JADX deobfuscation is non-deterministic across runs (counter-based renames vary
        # with internal HashMap ordering). Skip the consistency re-run check.
        result = self.do_execution(
            data_in=[("content", data)],
            verify_input_content=False,
            check_consistent_augmented_stream=False,
        )
        self.assertEqual(result.state, State(State.Label.COMPLETED))

        self.assertEqual(len(result.events), 1)
        event = result.events[0]

        # --- Decompiled source files (4 user-code files from com.sosauce.vanilla) ---
        self.assertEqual(len(event.data), 4)
        self.assertTrue(all(d.label == DataLabel.DECOMPILED_CS for d in event.data))

        # --- All features ---
        self.assertReprEqual(
            event.features,
            {
                "class_methods": [
                    FV("MainActivity::onCreate"),
                    FV("MainActivity::setContentView"),
                    FV("QSTile::onClick"),
                    FV("QSTile::startActivity"),
                    FV("QSTile::startActivityAndCollapse"),
                ],
                "classes": [
                    FV("HistoryDatabase"),
                    FV("HistoryDatabase_Impl"),
                    FV("MainActivity"),
                    FV("QSTile"),
                ],
                "package_class_methods": [
                    FV("com.sosauce.vanilla.MainActivity::onCreate"),
                    FV("com.sosauce.vanilla.MainActivity::setContentView"),
                    FV("com.sosauce.vanilla.data.sysui.QSTile::onClick"),
                    FV("com.sosauce.vanilla.data.sysui.QSTile::startActivity"),
                    FV("com.sosauce.vanilla.data.sysui.QSTile::startActivityAndCollapse"),
                ],
                "package_classes": [
                    FV("com.sosauce.vanilla.MainActivity"),
                    FV("com.sosauce.vanilla.data.sysui.QSTile"),
                    FV("com.sosauce.vanilla.domain.repository.HistoryDatabase"),
                    FV("com.sosauce.vanilla.domain.repository.HistoryDatabase_Impl"),
                ],
                "package_methods": [
                    FV("com.sosauce.vanilla.data.sysui::onClick"),
                    FV("com.sosauce.vanilla.data.sysui::startActivity"),
                    FV("com.sosauce.vanilla.data.sysui::startActivityAndCollapse"),
                    FV("com.sosauce.vanilla::onCreate"),
                    FV("com.sosauce.vanilla::setContentView"),
                ],
                "packages": [
                    FV("com"),
                    FV("com.sosauce"),
                    FV("com.sosauce.vanilla"),
                    FV("com.sosauce.vanilla.data"),
                    FV("com.sosauce.vanilla.data.sysui"),
                    FV("com.sosauce.vanilla.domain"),
                    FV("com.sosauce.vanilla.domain.repository"),
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

        # --- Decompiled source files (4 user-code files; R.java excluded) ---
        self.assertEqual(len(event.data), 4)
        self.assertTrue(all(d.label == DataLabel.DECOMPILED_CS for d in event.data))

        # --- All features ---
        self.assertReprEqual(
            event.features,
            {
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
                    FV("StressService"),
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
                    FV("net.tlfoxhuman.droidstress.StressService"),
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
                "packages": [
                    FV("net"),
                    FV("net.tlfoxhuman"),
                    FV("net.tlfoxhuman.droidstress"),
                ],
            },
        )
