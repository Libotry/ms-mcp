import os
import shutil
import importlib.util

def validate_profiling_artifacts(artifacts_dir):
    """
    Checks if a given path contains valid generated profiling data.
    - If path doesn't exist, it's invalid
    - If path is empty, it's invalid
    - Needs to contain some valid profiling files to be true
    """
    if not os.path.exists(artifacts_dir) or not os.path.isdir(artifacts_dir):
        return {"ok": False, "reason": "Directory does not exist. No profiling artifacts found."}
    
    count = 0
    # Check if there are any supported files in the directory
    for root, dirs, files in os.walk(artifacts_dir):
        count += len(files)
            
    if count > 0:
         return {"ok": True, "artifact_count": count, "reason": "Found artifacts"}
         
    return {"ok": False, "artifact_count": 0, "reason": "Directory is empty so no profiling artifacts."}

def evaluate_framework_requirements(framework="torch", command_exists=None, import_exists=None):
    """
    Checks if required framework packages (like torch, torch_npu, mindspore) are installed
    This checks via python import capabilities.
    """
    if command_exists is None:
        command_exists = lambda cmd: shutil.which(cmd) is not None
        
    if import_exists is None:
        import_exists = lambda pkg: importlib.util.find_spec(pkg) is not None
        
    missing_packages = []
    missing_commands = []
    
    if framework == "torch" or framework == "pytorch":
        # Check basic torch_npu as it's the primary indicator for PyTorch on Ascend
        if not import_exists("torch_npu"):
             missing_packages.append("torch_npu")
    elif framework == "mindspore":
        if not import_exists("mindspore"):
             missing_packages.append("mindspore")
             
    # For either framework we need msprof
    if not command_exists("msprof"):
         missing_commands.append("msprof")
    
    return {
        "ok": len(missing_packages) == 0 and len(missing_commands) == 0, 
        "missing_packages": missing_packages,
        "missing_commands": missing_commands,
        "missing": missing_packages + missing_commands,
        "reason": f"Missing packges: {missing_packages}, missing commands: {missing_commands}"
    }
    
def evaluate_ascend_environment(command_exists=None):
    """
    Checks if the actual Ascend NPU environment tools are available.
    Primarily looking for npu-smi, similar to nvidia-smi.
    """
    if command_exists is None:
         command_exists = lambda cmd: shutil.which(cmd) is not None
         
    missing_tools = []
    
    # Check for npu-smi
    if not command_exists("npu-smi"):
        missing_tools.append("npu-smi")
        
    return {
        "ok": len(missing_tools) == 0, 
        "missing_commands": missing_tools,
        "reason": f"Missing commands: {missing_tools}"
    }

if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == "check-env":
        env_ok, missing_env = evaluate_ascend_environment()
        if not env_ok:
            print(f"ERROR: Missing Ascend environment tools: {', '.join(missing_env)}. Ascend NPU environment required.")
            sys.exit(1)
            
        fw_ok, missing_fw = evaluate_framework_requirements()
        if not fw_ok:
            print(f"ERROR: Missing framework dependencies: {', '.join(missing_fw)}.")
            sys.exit(1)
            
        print("INFO: Ascend environment check passed.")
        sys.exit(0)
    
    elif len(sys.argv) > 2 and sys.argv[1] == "check-artifacts":
        artifact_path = sys.argv[2]
        if not validate_profiling_artifacts(artifact_path):
             print(f"ERROR: No valid profiling artifacts found in {artifact_path}. Profiling data cannot be faked.")
             sys.exit(1)
             
        print(f"INFO: Valid profiling artifacts found in {artifact_path}.")
        sys.exit(0)
    else:
        print("Usage: python check_real_profiling_env.py [check-env | check-artifacts <dir>]")
        sys.exit(1)
