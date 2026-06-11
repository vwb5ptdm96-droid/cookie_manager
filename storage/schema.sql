USE my_new_schema;
CREATE TABLE IF NOT EXISTS cookie_tasks (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    name VARCHAR(128) NOT NULL,
    site VARCHAR(64) NOT NULL,
    account VARCHAR(128) NOT NULL,
    username VARCHAR(255) NOT NULL DEFAULT '',
    password VARCHAR(255) NOT NULL DEFAULT '',
    probe_url VARCHAR(1000) NOT NULL,
    method VARCHAR(16) NOT NULL DEFAULT 'GET',
    ok_statuses VARCHAR(64) NOT NULL DEFAULT '200',
    headers_json JSON DEFAULT NULL,
    timeout_seconds INT UNSIGNED NOT NULL DEFAULT 15,
    refresh_script VARCHAR(128) NOT NULL,
    enabled TINYINT(1) NOT NULL DEFAULT 1,
    browser_path VARCHAR(1000) NOT NULL DEFAULT '',
    user_data_dir VARCHAR(1000) NOT NULL DEFAULT '',
    profile_dir VARCHAR(128) NOT NULL DEFAULT 'Default',
    cdp_port INT UNSIGNED NOT NULL DEFAULT 9222,
    login_url VARCHAR(1000) NOT NULL DEFAULT '',
    last_status SMALLINT UNSIGNED DEFAULT NULL,
    last_action VARCHAR(16) DEFAULT NULL,
    last_result VARCHAR(16) NOT NULL DEFAULT 'idle',
    last_error TEXT DEFAULT NULL,
    checked_at DATETIME DEFAULT NULL,
    refreshed_at DATETIME DEFAULT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
        ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY uk_task_site_account (site, account),
    KEY idx_task_enabled (enabled),
    KEY idx_task_result (last_result)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;




CREATE TABLE IF NOT EXISTS crawler_cookies (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    site VARCHAR(64) NOT NULL,
    account VARCHAR(128) NOT NULL,
    cookie LONGTEXT NOT NULL,
    last_status SMALLINT UNSIGNED DEFAULT NULL,
    checked_at DATETIME DEFAULT NULL,
    refreshed_at DATETIME DEFAULT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
        ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY uk_cookie_site_account (site, account)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS task_runs (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    task_id BIGINT UNSIGNED NOT NULL,
    action VARCHAR(16) NOT NULL,
    status VARCHAR(16) NOT NULL DEFAULT 'queued',
    http_status SMALLINT UNSIGNED DEFAULT NULL,
    message TEXT DEFAULT NULL,
    started_at DATETIME DEFAULT NULL,
    finished_at DATETIME DEFAULT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    KEY idx_run_task_created (task_id, created_at),
    KEY idx_run_status (status),
    CONSTRAINT fk_task_runs_task
        FOREIGN KEY (task_id) REFERENCES cookie_tasks(id)
        ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

