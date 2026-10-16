import json
import unittest
from unittest.mock import MagicMock, patch

import github_pr


class GitHubPRTests(unittest.TestCase):
    def test_pr_url_accepts_only_github_pull_requests(self):
        self.assertEqual(github_pr.parse_pr_url("https://github.com/owner/repo/pull/42"),
                         ("owner", "repo", 42))
        for url in ("https://github.com.evil.test/owner/repo/pull/42",
                    "http://github.com/owner/repo/pull/42",
                    "https://github.com/owner/repo/issues/42",
                    "https://github.com/owner/repo/pull/42?x=1"):
            with self.subTest(url=url), self.assertRaises(ValueError):
                github_pr.parse_pr_url(url)

    def test_checkout_uses_exact_head_and_merge_base(self):
        base, head, ancestor = "a" * 40, "b" * 40, "c" * 40
        pr = {"owner": "owner", "repo": "repo", "number": 42,
              "base_ref": "main", "base_sha": base, "head_sha": head}
        calls = []

        def fake_git(args, cwd=None, timeout=180):
            calls.append(args)
            if "clone" in args:
                from pathlib import Path
                Path(args[-1]).mkdir()
            if args[:2] == ["rev-parse", "FETCH_HEAD"]:
                return head
            if args[:2] == ["cat-file", "-t"]:
                return "commit"
            if args[0] == "merge-base":
                return ancestor
            if args[0] == "diff":
                return "+++ b/app.py\n@@ -1 +1 @@\n-old\n+new\n"
            return ""

        with patch.object(github_pr, "_git", side_effect=fake_git):
            with github_pr.checkout_pr(pr) as (repo, diff):
                self.assertTrue(repo.is_dir())
                self.assertIn("+++ b/app.py", diff)
            self.assertFalse(repo.exists())
        self.assertIn(["fetch", "--no-tags", "origin", "pull/42/head"], calls)
        self.assertIn(["merge-base", base, head], calls)
        self.assertIn(["diff", "--no-ext-diff", "--unified=3", ancestor, head], calls)

    def test_changed_head_is_rejected_before_review(self):
        pr = {"owner": "owner", "repo": "repo", "number": 42,
              "base_ref": "main", "base_sha": "a" * 40, "head_sha": "b" * 40}
        with patch.object(github_pr, "_git", side_effect=["", "", "c" * 40]):
            with self.assertRaisesRegex(RuntimeError, "changed during checkout"):
                with github_pr.checkout_pr(pr):
                    self.fail("A changed PR head must not be reviewed")

    def test_post_comment_uses_issue_timeline_api(self):
        pr = {"owner": "owner", "repo": "repo", "number": 42,
              "url": "https://github.com/owner/repo/pull/42"}
        response = MagicMock(returncode=0, stdout=json.dumps({"html_url": "https://github.com/owner/repo/pull/42#issuecomment-1"}))
        with patch.object(github_pr.subprocess, "run", return_value=response) as run:
            result = github_pr.post_comment(pr, "A report")
        self.assertEqual(result, "https://github.com/owner/repo/pull/42#issuecomment-1")
        args = run.call_args.args[0]
        self.assertEqual(args[:3], ["gh", "api", "repos/owner/repo/issues/42/comments"])
        self.assertEqual(json.loads(run.call_args.kwargs["input"]), {"body": "A report"})


if __name__ == "__main__":
    unittest.main()
