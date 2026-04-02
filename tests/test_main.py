"""Tests for AzulPluginJadx."""

from azul_runner import JobResult, State, test_template

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
