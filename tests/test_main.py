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

    def test_apk_calltimer(self):
        """A real APK should decompile successfully with manifest features and source files."""
        # TODO: upload Call-Timer_2.0.98R_APKPure.apk to Azure and replace hash below.
        # Real SHA-256: 5d3ebd759e4d05263a71f913f6dfd3269cc145f8f5ff7ef1974f07c5706178e1
        data = self.load_test_file_bytes(
            "5d3ebd759e4d05263a71f913f6dfd3269cc145f8f5ff7ef1974f07c5706178e1",
            "Call-Timer 2.0.98R APK (ctsoft.androidapps.calltimer) from APKPure.",
        )
        result = self.do_execution(
            data_in=[("content", data)],
            verify_input_content=False,
        )
        self.assertEqual(result.state, State(State.Label.COMPLETED))

        self.assertEqual(len(result.events), 1)
        event = result.events[0]

        # --- Manifest features ---
        self.assertIn(FV("ctsoft.androidapps.calltimer"), event.features["package_name"])
        self.assertIn(FV("2.0.98R"), event.features["version_name"])
        self.assertIn(FV("2103198"), event.features["version_code"])
        self.assertIn(FV("30"), event.features["min_sdk_version"])
        self.assertIn(FV("35"), event.features["target_sdk_version"])

        # --- Code features: at least some classes and methods extracted ---
        self.assertGreater(len(event.features.get("classes", [])), 0)
        self.assertGreater(len(event.features.get("class_methods", [])), 0)
        self.assertGreater(len(event.features.get("packages", [])), 0)

        # --- Decompiled source files added ---
        self.assertGreater(len(event.data), 0)
        self.assertTrue(any(d.label == DataLabel.DECOMPILED_CS for d in event.data))
