from textual.messages import Message

# ! === Messages ==============================================================
class ASIC_Number_Changed(Message):
    """Message indicating the ASIC number has changed."""

    def __init__(self, sender, fpga_id: str, asic_num: int) -> None:
        super().__init__()
        self.sender = sender
        self.fpga_id = fpga_id
        self.asic_num = asic_num

class ASIC_Number_Request(Message):
    """Message requesting the current ASIC number."""

    def __init__(self, sender, fpga_id: str) -> None:
        super().__init__()
        self.sender = sender
        self.fpga_id = fpga_id

class UdpJsonSelected(Message):
    """Message indicating a UDP JSON file has been selected."""

    def __init__(self, sender, fpga_id: str, json_path: str) -> None:
        super().__init__()
        self.sender = sender
        self.fpga_id = fpga_id
        self.json_path = json_path