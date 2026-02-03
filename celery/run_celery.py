import os
import sys
import importlib

def get_app():
    app_path = os.environ.get("CELERY_APP")
    if not app_path:
        print("Error: CELERY_APP environment variable is not set.")
        sys.exit(1)
    
    try:
        # Support both module:attr and module.attr
        if ":" in app_path:
            module_name, app_attr = app_path.split(":", 1)
        else:
            module_name, app_attr = app_path.rsplit(".", 1)
            
        module = importlib.import_module(module_name)
        return getattr(module, app_attr)
    except Exception as e:
        print(f"Error loading Celery app '{app_path}': {e}")
        sys.exit(1)

def main():
    celery_app = get_app()
    
    # Add dynamic imports
    imports_str = os.environ.get("CELERY_IMPORTS", "")
    extra_imports = [i.strip() for i in imports_str.split(",") if i.strip()]
    
    if extra_imports:
        print(f"Adding imports: {extra_imports}")
        # Ensure include is a list
        current_include = list(celery_app.conf.include) if celery_app.conf.include else []
        celery_app.conf.update(include=current_include + extra_imports)
    
    # Run the worker/beat
    opts = os.environ.get("CELERY_OPTS", "worker --loglevel=info").split()
    print(f"Starting Celery with options: {opts}")
    
    # celery_app.start(argv=...) expects argv to simulate command line args
    # argv[0] is program name
    celery_app.start(argv=["celery"] + opts)

if __name__ == "__main__":
    main()
