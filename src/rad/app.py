#!/usr/bin/env python3
import os
import sys
import json
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from urllib.request import urlopen, Request
from urllib.parse import urlparse
from urllib.error import HTTPError
import threading

CONFIG_FILE = os.path.join(os.path.expanduser("~"), "repos_gui.json")

class ReleaseDownloaderApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Release Asset Downloader")
        self.root.geometry("660x360")
        self.root.resizable(True, True)
        
        self.repo_config = {}
        self.fetched_assets = {}
        self.download_in_progress = False
        self.animation_counter = 0
        
        self.create_widgets()
        self.reload_config_from_file()

    def load_config(self):
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, "r") as f:
                    return json.load(f)
            except Exception:
                return {}
        return {}

    def save_config(self):
        with open(CONFIG_FILE, "w") as f:
            json.dump(self.repo_config, f, indent=2)

    def reload_config_from_file(self):
        self.repo_config = self.load_config()
        self.update_repo_dropdown()
        self.update_status(f"Loaded {len(self.repo_config)} repositories from configuration.")

    def create_widgets(self):
        main_frame = ttk.Frame(self.root, padding="15")
        main_frame.pack(fill=tk.BOTH, expand=True)

        # --- SECTION 1: ADD / REGISTER REPO (Streamlined Row) ---
        repo_frame = ttk.LabelFrame(main_frame, text=" Register New Repository ", padding="10")
        repo_frame.pack(fill=tk.X, pady=(0, 15))

        ttk.Label(repo_frame, text="GitHub URL:").pack(side=tk.LEFT, padx=(0, 5))
        
        self.url_entry = ttk.Entry(repo_frame)
        self.url_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        self.url_entry.insert(0, "https://github.com/OWNER/REPO")
        self.url_entry.bind("<Return>", lambda event: self.start_register_thread())

        # Paste Button
        self.paste_btn = ttk.Button(repo_frame, text="📋", width=3, command=self.paste_from_clipboard)
        self.paste_btn.pack(side=tk.LEFT, padx=2)

        # Save Button
        self.add_btn = ttk.Button(repo_frame, text="Save", command=self.start_register_thread)
        self.add_btn.pack(side=tk.LEFT, padx=(5, 0))

        # --- SECTION 2: FETCH & DOWNLOAD ---
        download_frame = ttk.LabelFrame(main_frame, text=" Fetch & Download Assets ", padding="10")
        download_frame.pack(fill=tk.BOTH, expand=True)

        # Select Repo Row
        ttk.Label(download_frame, text="Select Repo:").grid(row=0, column=0, sticky=tk.W, pady=10)
        
        dropdown_frame = ttk.Frame(download_frame)
        dropdown_frame.grid(row=0, column=1, sticky=tk.EW, padx=5, pady=10)
        
        self.repo_dropdown = ttk.Combobox(dropdown_frame, state="readonly")
        self.repo_dropdown.pack(side=tk.LEFT, fill=tk.X, expand=True)
        
        # Refresh Button
        self.refresh_btn = ttk.Button(dropdown_frame, text="⟳", width=3, command=self.reload_config_from_file)
        self.refresh_btn.pack(side=tk.LEFT, padx=(5, 0))
        
        # Delete Repo Button (-)
        self.delete_btn = ttk.Button(dropdown_frame, text="—", width=3, command=self.delete_selected_repo)
        self.delete_btn.pack(side=tk.LEFT, padx=(5, 0))
        
        self.fetch_btn = ttk.Button(download_frame, text="Fetch Latest Release", command=self.fetch_assets_from_api)
        self.fetch_btn.grid(row=0, column=2, sticky=tk.E, padx=5, pady=10)

        # Select Asset Row
        ttk.Label(download_frame, text="Select Asset:").grid(row=1, column=0, sticky=tk.W, pady=10)
        self.asset_dropdown = ttk.Combobox(download_frame, state="readonly")
        self.asset_dropdown.grid(row=1, column=1, columnspan=2, sticky=tk.EW, padx=5, pady=10)

        # Download Actions Row
        action_frame = ttk.Frame(download_frame)
        action_frame.grid(row=2, column=0, columnspan=3, pady=15, sticky=tk.EW)

        self.download_btn = ttk.Button(action_frame, text="Download Asset", state=tk.DISABLED, command=self.start_download_thread)
        self.download_btn.pack(side=tk.LEFT, padx=5)

        self.open_folder_btn = ttk.Button(action_frame, text="Open File Location", state=tk.DISABLED, command=self.open_download_folder)
        self.open_folder_btn.pack(side=tk.LEFT, padx=5)

        # Status Bar
        self.status_label = ttk.Label(main_frame, text="Ready", relief=tk.SUNKEN, anchor=tk.W, padding="2")
        self.status_label.pack(side=tk.BOTTOM, fill=tk.X, pady=(10, 0))

        download_frame.columnconfigure(1, weight=1)

    # -------------------------------------------------------------------------
    # Logic & Event Handlers
    # -------------------------------------------------------------------------
    def update_status(self, text):
        self.status_label.config(text=text)
        self.root.update_idletasks()

    def paste_from_clipboard(self):
        try:
            clipboard_content = self.root.clipboard_get().strip()
            self.url_entry.delete(0, tk.END)
            self.url_entry.insert(0, clipboard_content)
            self.update_status("Pasted URL from clipboard.")
        except tk.TclError:
            self.update_status("Clipboard is empty or doesn't contain valid text.")

    def update_repo_dropdown(self):
        repos = list(self.repo_config.keys())
        self.repo_dropdown['values'] = repos
        if repos:
            current_val = self.repo_dropdown.get()
            if current_val in repos:
                self.repo_dropdown.set(current_val)
            else:
                self.repo_dropdown.current(0)
        else:
            self.repo_dropdown.set('')
            self.asset_dropdown['values'] = []
            self.asset_dropdown.set('')
            self.download_btn.config(state=tk.DISABLED)

    def start_register_thread(self):
        url = self.url_entry.get().strip()

        if not url:
            messagebox.showwarning("Validation Error", "GitHub URL field is required.")
            return

        parsed_url = urlparse(url)
        path_parts = [p for p in parsed_url.path.split('/') if p]
        
        if "github.com" not in parsed_url.netloc or len(path_parts) < 2:
            messagebox.showerror("Invalid URL", "Format must match: https://github.com/owner/repo")
            return

        owner, repo_name = path_parts[0], path_parts[1]
        
        # Automatically format key as 'OWNER/REPO'
        slug_key = f"{owner}/{repo_name}"
        
        self.add_btn.config(state=tk.DISABLED)
        self.update_status(f"Verifying {slug_key} existence on GitHub...")
        
        threading.Thread(target=self.verify_and_save_repo, args=(owner, repo_name, slug_key), daemon=True).start()

    def verify_and_save_repo(self, owner, repo_name, slug_key):
        api_url = f"https://api.github.com/repos/{owner}/{repo_name}"
        req = Request(api_url, headers={"User-Agent": "Tkinter-Release-Downloader"})
        
        try:
            with urlopen(req) as response:
                if response.status == 200:
                    self.repo_config[slug_key] = {"owner": owner, "repo": repo_name}
                    self.save_config()
                    self.root.after(0, lambda: self.finalize_registration(slug_key))
        except HTTPError as e:
            if e.code == 404:
                self.root.after(0, lambda: messagebox.showerror("Verification Failed", f"Repository '{slug_key}' was not found on GitHub (404)."))
            else:
                self.root.after(0, lambda: messagebox.showerror("API Error", f"Could not verify repository. HTTP Code: {e.code}"))
        except Exception as e:
            self.root.after(0, lambda: messagebox.showerror("Network Error", f"Failed connection attempt:\n{e}"))
        finally:
            self.root.after(0, lambda: self.add_btn.config(state=tk.NORMAL))

    def finalize_registration(self, slug_key):
        self.update_repo_dropdown()
        self.repo_dropdown.set(slug_key)
        self.update_status(f"Saved mapping for: '{slug_key}'")

    def delete_selected_repo(self):
        selected_repo = self.repo_dropdown.get()
        if not selected_repo:
            messagebox.showwarning("Selection Missing", "Please select a repository to remove.")
            return
            
        if selected_repo in self.repo_config:
            del self.repo_config[selected_repo]
            self.save_config()
            self.update_repo_dropdown()
            self.update_status(f"Removed '{selected_repo}' from saved mappings.")

    def fetch_assets_from_api(self):
        selected_repo = self.repo_dropdown.get()
        if not selected_repo:
            messagebox.showwarning("Selection Missing", "Please select a repository first.")
            return

        repo_data = self.repo_config[selected_repo]
        owner, repo = repo_data["owner"], repo_data["repo"]
        api_url = f"https://api.github.com/repos/{owner}/{repo}/releases/latest"
        
        self.update_status(f"Contacting GitHub API for {selected_repo}...")

        try:
            req = Request(api_url, headers={"User-Agent": "Tkinter-Release-Downloader"})
            with urlopen(req) as r:
                release_info = json.loads(r.read().decode())
        except Exception as e:
            messagebox.showerror("API Error", f"Failed to fetch metadata from GitHub:\n{e}")
            self.update_status("Error fetching release assets.")
            return

        self.fetched_assets.clear()
        asset_names = []

        assets = release_info.get("assets", [])
        for asset in assets:
            name = asset["name"]
            self.fetched_assets[name] = asset["browser_download_url"]
            asset_names.append(name)

        tag = release_info.get("tag_name", "latest")
        if "zipball_url" in release_info:
            name = f"Source code ({tag}).zip"
            self.fetched_assets[name] = release_info["zipball_url"]
            asset_names.append(name)
            
        if "tarball_url" in release_info:
            name = f"Source code ({tag}).tar.gz"
            self.fetched_assets[name] = release_info["tarball_url"]
            asset_names.append(name)

        if not asset_names:
            messagebox.showinfo("No Assets", f"The latest release ({tag}) has absolutely no downloadable files.")
            self.update_status("No assets available.")
            return

        self.asset_dropdown['values'] = asset_names
        self.asset_dropdown.current(0)
        
        self.download_btn.config(state=tk.NORMAL)
        self.update_status(f"Found {len(asset_names)} assets for release version: {tag}")

    def start_download_thread(self):
        selected_asset = self.asset_dropdown.get()
        if not selected_asset or selected_asset not in self.fetched_assets:
            messagebox.showwarning("Asset Missing", "Please pick a valid asset to download.")
            return

        download_url = self.fetched_assets[selected_asset]
        save_path = filedialog.asksaveasfilename(
            initialdir=os.getcwd(),
            initialfile=selected_asset,
            title="Save Asset As"
        )
        
        if not save_path:
            return

        self.download_in_progress = True
        self.download_btn.config(state=tk.DISABLED)
        self.refresh_btn.config(state=tk.DISABLED)
        self.delete_btn.config(state=tk.DISABLED)
        self.fetch_btn.config(state=tk.DISABLED)
        self.animation_counter = 0
        
        threading.Thread(target=self.execute_download, args=(download_url, save_path), daemon=True).start()
        self.animate_status_bar()

    def animate_status_bar(self):
        if not self.download_in_progress:
            return
        
        self.animation_counter = (self.animation_counter % 10) + 1
        dots = "." * self.animation_counter
        self.status_label.config(text=f"Downloading{dots}")
        self.root.after(250, self.animate_status_bar)

    def execute_download(self, url, path):
        try:
            req = Request(url, headers={"User-Agent": "Tkinter-Release-Downloader"})
            with urlopen(req) as response, open(path, 'wb') as out_file:
                out_file.write(response.read())
            
            self.root.after(0, lambda: self.finalize_download(True, path))
        except Exception as e:
            self.root.after(0, lambda: self.finalize_download(False, str(e)))

    def finalize_download(self, success, payload):
        self.download_in_progress = False
        self.download_btn.config(state=tk.NORMAL)
        self.refresh_btn.config(state=tk.NORMAL)
        self.delete_btn.config(state=tk.NORMAL)
        self.fetch_btn.config(state=tk.NORMAL)
        
        if success:
            self.last_download_directory = os.path.dirname(payload)
            self.open_folder_btn.config(state=tk.NORMAL)
            filename = os.path.basename(payload)
            self.update_status(f"Successfully downloaded {filename}!")
        else:
            self.update_status("Download failed.")
            messagebox.showerror("Download Error", f"An error occurred:\n{payload}")

    def open_download_folder(self):
        if hasattr(self, 'last_download_directory') and os.path.exists(self.last_download_directory):
            if sys.platform == 'win32':
                os.startfile(self.last_download_directory)
            elif sys.platform == 'darwin':
                import subprocess
                subprocess.Popen(['open', self.last_download_directory])
            else:
                import subprocess
                subprocess.Popen(['xdg-open', self.last_download_directory])


def main():
    root = tk.Tk()
    app = ReleaseDownloaderApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
