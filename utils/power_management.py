import subprocess

class PowerManagement:

    def get_performance_adjustment_mode(self):
        result = int(self.__execute_apm_command__("-P"))
        if result == 1:
            return "Automatic"
        return "Manual"

    def __execute_apm_command__(self, flag):
        return subprocess.run(["apm", flag], capture_output=True, text=True).stdout.strip()
