import os

# Model discovery calls provider APIs at import time; tests must stay offline.
os.environ["MODEL_DISCOVERY"] = "0"
