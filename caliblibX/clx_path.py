import os

def output_path_setup(script_id_str, timestamp_str, base_dir=None):
    # under dump in the script directory
    if base_dir is None:
        base_dir = os.path.dirname(os.path.abspath(__file__))
    dump_dir = os.path.join(base_dir, 'dump')
    output_folder_name = f"{script_id_str}_{timestamp_str}"
    output_dump_folder = os.path.join(dump_dir, output_folder_name)
    output_config_name = f"{script_id_str}_config_{timestamp_str}.json"
    output_config_path = os.path.join(output_dump_folder, output_config_name)

    os.makedirs(output_dump_folder, exist_ok=True)

    return output_dump_folder, output_config_path