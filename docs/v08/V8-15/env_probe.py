"""记录 V8-15 运行环境：Python/NumPy/SciPy/shapely 版本、BLAS 配置、线程环境变量。只读。"""
import io, os, platform, sys, contextlib
import numpy, scipy, shapely
print("python", sys.version.replace("\n", " "))
print("executable", sys.executable)
print("platform", platform.platform())
print("numpy", numpy.__version__, "scipy", scipy.__version__, "shapely", shapely.__version__)
for k in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
    print(k, os.environ.get(k))
try:
    import psutil
    print("psutil", psutil.__version__)
except ImportError:
    print("psutil absent")
buf = io.StringIO()
with contextlib.redirect_stdout(buf):
    numpy.show_config()
print("--- numpy.show_config ---")
print(buf.getvalue())
