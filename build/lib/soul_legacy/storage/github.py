"""
GitHub private repo storage backend.
Pushes encrypted vault to a private GitHub repo on every write.
The repo contains only ciphertext — GitHub sees nothing useful.
"""
import os, subprocess


class GitHubStorage:
    def __init__(self, vault_dir: str, repo_url: str):
        self.vault_dir = vault_dir
        self.repo_url  = repo_url

    def init_repo(self):
        subprocess.run(["git", "init"], cwd=self.vault_dir, check=True)
        subprocess.run(["git", "remote", "add", "origin", self.repo_url],
                       cwd=self.vault_dir, check=True)
        gitignore = os.path.join(self.vault_dir, ".gitignore")
        open(gitignore, "w").write(".salt\n")  # never commit the salt
        subprocess.run(["git", "add", ".gitignore"], cwd=self.vault_dir)

    def push(self, message: str = "vault update"):
        subprocess.run(["git", "add", "-A"], cwd=self.vault_dir)
        subprocess.run(["git", "commit", "-m", message], cwd=self.vault_dir)
        subprocess.run(["git", "push", "-u", "origin", "main"], cwd=self.vault_dir)

    def pull(self):
        subprocess.run(["git", "pull"], cwd=self.vault_dir)
