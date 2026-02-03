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
    
    # Update sys.argv so click picks it up correctly
    # We use 'celery' as the program name
    sys.argv = ["celery"] + opts
    
    try:
        celery_app.start()
    except Exception as e:
        # Fallback for some versions or specific error cases
        print(f"Error starting via app.start(): {e}")
        if opts[0] == 'worker':
            print("Attempting fallback to worker_main...")
            # worker_main expects sys.argv style, so ['worker', ...] might be needed
            # usually program name is first, so ['celery', 'worker', ...]
            celery_app.worker_main(argv=sys.argv)
        else:
            raise

if __name__ == "__main__":
    main()
