"""
Regression tests for the deleted-user / sold-volume data-corruption bug.

Bug recap: a failed or invalid GET /api/users for an admin used to come back
as an empty list. track_deleted_users() then saw every one of that admin's
users as "deleted" and permanently added their used traffic to
deleted_users_used_bytes (sold volume), and the next successful sync could
never undo it.

These tests only exercise error handling / control flow. No formula
(total_user_limit, sold_limit_bytes, hidden_traffic, admin_remaining,
usage_percent, enforcement thresholds) is touched by the fix, and none is
asserted to have changed value here — only whether it was computed at all.

Run against an isolated in-memory SQLite DB, never the live MySQL instance:

    python manage.py test admins --settings=pamp.test_settings
"""
from unittest.mock import patch, MagicMock

import requests
from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from admins import tasks
from admins.models import PanelAdmin, SyncLog, UserTrafficSnapshot
from admins.panel_api import DEFAULT_USERS_LIMIT, PanelAPIClient, PanelAPIError


def _admin_payload(username='alice', used_traffic=500, total_users=2, data_limit=None,
                    is_disabled=False, status='active'):
    return {
        'username': username,
        'is_owner': False,
        'is_disabled': is_disabled,
        'status': status,
        'data_limit': data_limit,
        'used_traffic': used_traffic,
        'total_users': total_users,
    }


# ─────────────────────────────────────────────────────────────────────────
# PanelAPIClient.get_users() — the raw HTTP layer actually raises on failure
# ─────────────────────────────────────────────────────────────────────────

class PanelAPIHttpErrorTests(TestCase):
    def _client(self):
        client = PanelAPIClient()
        client._token = 'test-token'  # skip the auth round-trip
        return client

    @patch('requests.Session.get')
    def test_5xx_raises_panel_api_error_not_empty_list(self, mock_get):
        resp = MagicMock(status_code=500)
        resp.raise_for_status.side_effect = requests.HTTPError("500 Server Error")
        mock_get.return_value = resp

        with self.assertRaises(PanelAPIError):
            self._client().get_users(admin_username='alice')

    @patch('requests.Session.get')
    def test_timeout_raises_panel_api_error_not_empty_list(self, mock_get):
        mock_get.side_effect = requests.Timeout("timed out")

        with self.assertRaises(PanelAPIError):
            self._client().get_users(admin_username='alice')

    @patch('requests.Session.get')
    def test_network_drop_raises_panel_api_error_not_empty_list(self, mock_get):
        mock_get.side_effect = requests.ConnectionError("connection reset")

        with self.assertRaises(PanelAPIError):
            self._client().get_users(admin_username='alice')


# ─────────────────────────────────────────────────────────────────────────
# PanelAPIClient.get_admin_user_stats() — must propagate, never swallow to []
# ─────────────────────────────────────────────────────────────────────────

class GetAdminUserStatsTests(TestCase):
    @patch.object(PanelAPIClient, 'get_users')
    def test_users_fetch_failure_propagates(self, mock_get_users):
        mock_get_users.side_effect = PanelAPIError("GET /api/users failed: 500 Server Error")
        with self.assertRaises(PanelAPIError):
            PanelAPIClient().get_admin_user_stats('alice')

    @patch.object(PanelAPIClient, 'get_users')
    def test_invalid_shape_raises_instead_of_silently_returning_empty(self, mock_get_users):
        mock_get_users.return_value = None  # malformed/unexpected response
        with self.assertRaises(PanelAPIError):
            PanelAPIClient().get_admin_user_stats('alice')

    @patch.object(PanelAPIClient, 'get_users')
    def test_truncated_list_is_flagged(self, mock_get_users):
        mock_get_users.return_value = [
            {'username': f'u{i}', 'data_limit': 0, 'used_traffic': 0, 'status': 'active'}
            for i in range(DEFAULT_USERS_LIMIT)
        ]
        stats = PanelAPIClient().get_admin_user_stats('alice')
        self.assertTrue(stats['truncated'])

    @patch.object(PanelAPIClient, 'get_users')
    def test_normal_list_not_truncated_and_formula_unchanged(self, mock_get_users):
        mock_get_users.return_value = [
            {'username': 'u1', 'data_limit': 300, 'used_traffic': 100, 'status': 'active'},
            {'username': 'u2', 'data_limit': 200, 'used_traffic': 50, 'status': 'limited'},
        ]
        stats = PanelAPIClient().get_admin_user_stats('alice')
        self.assertFalse(stats['truncated'])
        self.assertEqual(stats['total_user_limit'], 500)   # sum(data_limit) — unchanged formula
        self.assertEqual(stats['total_user_used'], 150)    # sum(used_traffic) — unchanged formula
        self.assertEqual(stats['active_user_count'], 1)
        self.assertEqual(stats['limited_users'], 1)


# ─────────────────────────────────────────────────────────────────────────
# PanelAPIClient.sync_all_admins() — per-admin failure must not poison the batch
# ─────────────────────────────────────────────────────────────────────────

class SyncAllAdminsTests(TestCase):
    @patch.object(PanelAPIClient, 'get_users')
    @patch.object(PanelAPIClient, 'get_admins')
    def test_users_fetch_failure_flags_admin_without_crashing_batch(self, mock_get_admins, mock_get_users):
        mock_get_admins.return_value = [_admin_payload('alice'), _admin_payload('bob')]
        # alice's users call fails; bob's succeeds
        mock_get_users.side_effect = [
            PanelAPIError("GET /api/users failed: 500 Server Error"),
            [{'username': 'u1', 'data_limit': 100, 'used_traffic': 10, 'status': 'active'}],
        ]
        results = PanelAPIClient().sync_all_admins()

        self.assertEqual(len(results), 2)
        alice = next(r for r in results if r['username'] == 'alice')
        bob = next(r for r in results if r['username'] == 'bob')

        self.assertIn('user_stats_error', alice)
        self.assertNotIn('total_user_limit', alice)   # no fabricated/empty stats
        self.assertNotIn('user_stats_error', bob)
        self.assertEqual(bob['total_user_limit'], 100)

    @patch.object(PanelAPIClient, 'get_admins')
    def test_empty_admins_list_returns_empty_results(self, mock_get_admins):
        mock_get_admins.return_value = []
        self.assertEqual(PanelAPIClient().sync_all_admins(), [])

    @patch.object(PanelAPIClient, 'get_users')
    @patch.object(PanelAPIClient, 'get_admins')
    def test_truncated_list_marked_skip_deleted_detection(self, mock_get_admins, mock_get_users):
        mock_get_admins.return_value = [_admin_payload('alice')]
        mock_get_users.return_value = [
            {'username': f'u{i}', 'data_limit': 0, 'used_traffic': 0, 'status': 'active'}
            for i in range(DEFAULT_USERS_LIMIT)
        ]
        results = PanelAPIClient().sync_all_admins()
        self.assertTrue(results[0]['skip_deleted_detection'])

    @patch.object(PanelAPIClient, 'get_users')
    @patch.object(PanelAPIClient, 'get_admins')
    def test_normal_sync_formulas_unchanged(self, mock_get_admins, mock_get_users):
        mock_get_admins.return_value = [_admin_payload('alice', used_traffic=400, data_limit=1000)]
        mock_get_users.return_value = [
            {'username': 'u1', 'data_limit': 300, 'used_traffic': 100, 'status': 'active'},
            {'username': 'u2', 'data_limit': 200, 'used_traffic': 50, 'status': 'active'},
        ]
        r = PanelAPIClient().sync_all_admins()[0]
        self.assertFalse(r['skip_deleted_detection'])
        self.assertEqual(r['total_user_limit'], 500)
        self.assertEqual(r['total_user_used'], 400)       # admin-level used_traffic, unchanged formula
        self.assertEqual(r['admin_remaining'], 600)        # max(0, 1000 - 400), unchanged formula


# ─────────────────────────────────────────────────────────────────────────
# tasks.sync_panel_admins — end-to-end: DB rows/snapshots/SyncLog
# ─────────────────────────────────────────────────────────────────────────

class SyncPanelAdminsTaskTests(TestCase):
    def setUp(self):
        # Limit enforcement (check_and_enforce_limits) tries to authenticate against
        # the real panel and is unrelated to the deleted-user/sold-volume bug under
        # test here; stub it out so its failure (no panel configured in tests) doesn't
        # pollute SyncLog.error_message / status for these assertions.
        patcher = patch('admins.tasks.check_and_enforce_limits')
        patcher.start()
        self.addCleanup(patcher.stop)

    def _make_admin(self, username='alice', total_user_limit=1000, total_user_used=400,
                     deleted_users_used_bytes=0, admin_limit_bytes=2000, admin_remaining=1600):
        return PanelAdmin.objects.create(
            username=username, is_sudo=False, is_active=True, status='active',
            has_data_limit=True, admin_limit_bytes=admin_limit_bytes, admin_remaining=admin_remaining,
            total_user_limit=total_user_limit, total_user_used=total_user_used,
            user_count=2, active_user_count=2,
            deleted_users_used_bytes=deleted_users_used_bytes,
        )

    # ── the core bug: a failed /api/users must not inflate deleted_users_used_bytes ──

    @patch.object(PanelAPIClient, 'sync_all_admins')
    def test_users_fetch_failure_leaves_admin_and_snapshots_untouched(self, mock_sync):
        admin = self._make_admin()
        UserTrafficSnapshot.objects.create(panel_admin=admin, user_username='u1', used_traffic_bytes=100)
        UserTrafficSnapshot.objects.create(panel_admin=admin, user_username='u2', used_traffic_bytes=200)

        mock_sync.return_value = [{
            'username': 'alice',
            'user_stats_error': "GET /api/users failed: 500 Server Error",
        }]

        tasks.sync_panel_admins.apply()

        admin.refresh_from_db()
        self.assertEqual(admin.total_user_limit, 1000)        # unchanged
        self.assertEqual(admin.total_user_used, 400)           # unchanged
        self.assertEqual(admin.deleted_users_used_bytes, 0)    # NOT inflated — the bug
        self.assertEqual(PanelAdmin.objects.count(), 1)        # not deleted either
        self.assertEqual(
            set(UserTrafficSnapshot.objects.filter(panel_admin=admin).values_list('user_username', flat=True)),
            {'u1', 'u2'},
        )

        log = SyncLog.objects.latest('id')
        self.assertEqual(log.status, SyncLog.STATUS_PARTIAL)
        self.assertIn('alice', log.error_message)
        self.assertIn('/api/users failed', log.error_message)

    @patch.object(PanelAPIClient, 'sync_all_admins')
    def test_timeout_leaves_admin_and_snapshots_untouched(self, mock_sync):
        admin = self._make_admin()
        UserTrafficSnapshot.objects.create(panel_admin=admin, user_username='u1', used_traffic_bytes=100)

        mock_sync.return_value = [{'username': 'alice', 'user_stats_error': "GET /api/users failed: timed out"}]
        tasks.sync_panel_admins.apply()

        admin.refresh_from_db()
        self.assertEqual(admin.deleted_users_used_bytes, 0)
        self.assertEqual(admin.total_user_limit, 1000)
        self.assertEqual(UserTrafficSnapshot.objects.filter(panel_admin=admin).count(), 1)

    @patch.object(PanelAPIClient, 'sync_all_admins')
    def test_5xx_leaves_admin_and_snapshots_untouched(self, mock_sync):
        admin = self._make_admin()
        UserTrafficSnapshot.objects.create(panel_admin=admin, user_username='u1', used_traffic_bytes=100)

        mock_sync.return_value = [{'username': 'alice', 'user_stats_error': "GET /api/users failed: 503"}]
        tasks.sync_panel_admins.apply()

        admin.refresh_from_db()
        self.assertEqual(admin.deleted_users_used_bytes, 0)
        self.assertEqual(admin.total_user_limit, 1000)

    # ── empty /api/admins must never wipe PanelAdmin rows ──

    @patch.object(PanelAPIClient, 'sync_all_admins')
    def test_empty_admins_list_does_not_delete_rows(self, mock_sync):
        self._make_admin('alice')
        self._make_admin('bob')
        mock_sync.return_value = []

        tasks.sync_panel_admins.apply()

        self.assertEqual(PanelAdmin.objects.count(), 2)
        log = SyncLog.objects.latest('id')
        self.assertEqual(log.status, SyncLog.STATUS_PARTIAL)
        self.assertIn('no admins', log.error_message)

    # ── truncated list must skip deleted-user detection only ──

    @patch.object(PanelAPIClient, 'sync_all_admins')
    def test_truncated_list_skips_deletion_detection_but_still_updates_admin(self, mock_sync):
        admin = self._make_admin(total_user_limit=1000, total_user_used=400)
        UserTrafficSnapshot.objects.create(panel_admin=admin, user_username='u1', used_traffic_bytes=100)
        UserTrafficSnapshot.objects.create(panel_admin=admin, user_username='u2', used_traffic_bytes=200)

        # Only u1 comes back this run (u2 would look "deleted"), but flagged truncated.
        mock_sync.return_value = [{
            'username': 'alice', 'is_sudo': False, 'is_active': True, 'status': 'active',
            'has_data_limit': True, 'admin_limit_bytes': 2000, 'admin_remaining': 1600,
            'total_user_limit': 100, 'total_user_used': 400, 'user_count': 1,
            'active_user_count': 1, 'on_hold_users': 0, 'limited_users': 0,
            'disabled_users': 0, 'expired_users': 0, 'raw_data': {},
            'users': [{'username': 'u1', 'used_traffic': 100}],
            'skip_deleted_detection': True,
        }]

        tasks.sync_panel_admins.apply()

        admin.refresh_from_db()
        self.assertEqual(admin.deleted_users_used_bytes, 0)   # NOT accumulated — detection was skipped
        self.assertEqual(admin.total_user_limit, 100)          # fresh Pasargad value, no preserved add
        # snapshots untouched — track_deleted_users() never ran
        self.assertEqual(
            set(UserTrafficSnapshot.objects.filter(panel_admin=admin).values_list('user_username', flat=True)),
            {'u1', 'u2'},
        )

    # ── normal sync: identical results to the pre-fix behavior ──

    @patch.object(PanelAPIClient, 'sync_all_admins')
    def test_normal_sync_detects_real_deletion_and_accumulates_once(self, mock_sync):
        admin = self._make_admin(total_user_limit=1000, total_user_used=400)
        UserTrafficSnapshot.objects.create(panel_admin=admin, user_username='u1', used_traffic_bytes=100)
        UserTrafficSnapshot.objects.create(panel_admin=admin, user_username='u2', used_traffic_bytes=200)

        # u2 genuinely gone this run; full (non-truncated) successful fetch.
        mock_sync.return_value = [{
            'username': 'alice', 'is_sudo': False, 'is_active': True, 'status': 'active',
            'has_data_limit': True, 'admin_limit_bytes': 2000, 'admin_remaining': 1600,
            'total_user_limit': 300, 'total_user_used': 400, 'user_count': 1,
            'active_user_count': 1, 'on_hold_users': 0, 'limited_users': 0,
            'disabled_users': 0, 'expired_users': 0, 'raw_data': {},
            'users': [{'username': 'u1', 'used_traffic': 100}],
            'skip_deleted_detection': False,
        }]

        tasks.sync_panel_admins.apply()

        admin.refresh_from_db()
        self.assertEqual(admin.deleted_users_used_bytes, 200)      # u2's used_traffic accumulated once
        self.assertEqual(admin.total_user_limit, 300 + 200)         # fresh + preserved, no double-count
        self.assertEqual(
            list(UserTrafficSnapshot.objects.filter(panel_admin=admin).values_list('user_username', flat=True)),
            ['u1'],
        )

        log = SyncLog.objects.latest('id')
        self.assertEqual(log.status, SyncLog.STATUS_SUCCESS)
        self.assertEqual(log.admins_synced, 1)

    @patch.object(PanelAPIClient, 'sync_all_admins')
    def test_normal_sync_removes_admin_no_longer_on_panel(self, mock_sync):
        self._make_admin('alice')
        self._make_admin('bob')
        mock_sync.return_value = [{
            'username': 'alice', 'is_sudo': False, 'is_active': True, 'status': 'active',
            'has_data_limit': True, 'admin_limit_bytes': 2000, 'admin_remaining': 1600,
            'total_user_limit': 300, 'total_user_used': 400, 'user_count': 1,
            'active_user_count': 1, 'on_hold_users': 0, 'limited_users': 0,
            'disabled_users': 0, 'expired_users': 0, 'raw_data': {},
            'users': [], 'skip_deleted_detection': False,
        }]

        tasks.sync_panel_admins.apply()

        self.assertEqual(set(PanelAdmin.objects.values_list('username', flat=True)), {'alice'})


# ─────────────────────────────────────────────────────────────────────────
# /v2/panel/ 500 — panel_admin.support_telegram doesn't exist on PanelAdmin
# ─────────────────────────────────────────────────────────────────────────

class PortalV2ViewTests(TestCase):
    def test_portal_v2_renders_without_limit_config(self):
        """Reseller with no AdminLimit row must not get a 500 on /v2/panel/."""
        user = User.objects.create_user(username='alice', password='x')
        PanelAdmin.objects.create(username='alice', status='active')
        self.client.force_login(user)

        resp = self.client.get(reverse('portal_v2'))

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.context['support_telegram'], '@support')
