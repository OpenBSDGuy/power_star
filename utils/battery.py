import subprocess

class Battery:

    def get_battery_percentage(self):
        return int(self.__execute_apm_command__("-l"))

    def is_charging(self):
        result = int(self.__execute_apm_command__("-a"))
        if result == 0:
            return False
        return True

    def get_battery_remaining(self):
        try:
            minutes = int(self.__execute_apm_command__("-m"))
            hours, remainder = divmod(minutes, 60)
            hours_str = str(hours).zfill(2)
            minutes_str = str(remainder).zfill(2)
            return f"{hours_str}:{minutes_str}"
        except ValueError:
            return "unknown"

    def __execute_apm_command__(self, flag):
        return subprocess.run(["apm", flag], capture_output=True, text=True).stdout.strip()
