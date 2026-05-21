--- a
+++ b
@@ -93,7 +93,7 @@
        if use_hip:
            cmake_args += [
                f"-DAMDGPU_TARGETS={targets_str}",
                "-DGGML_HIP=ON",
-                "-DGGML_HIP_ROCWMMA_FATTN=ON",
+                "-DGGML_HIP_ROCWMMA_FATTN=OFF",
                "-DLLAMA_CURL=ON",   # AMD docs require this flag
            ]
        else:

