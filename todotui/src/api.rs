use anyhow::{bail, Result};
use reqwest::blocking::{Client, ClientBuilder};
use serde::Deserialize;
use std::collections::HashMap;

#[derive(Debug, Clone, Deserialize)]
pub struct Task {
    pub id: usize,
    pub description: String,
    pub completed: bool,
    pub priority: Option<String>,
    pub projects: Vec<String>,
    pub contexts: Vec<String>,
    pub raw_line: String,
}

#[derive(Deserialize)]
struct SearchResponse {
    tasks: Vec<Task>,
}

pub struct TodoApi {
    client: Client,
    base_url: String,
    username: String,
    password: String,
    authenticated: bool,
}

impl TodoApi {
    pub fn new(base_url: &str, username: &str, password: &str) -> Result<Self> {
        let client = ClientBuilder::new()
            .cookie_store(true)
            .build()?;
        Ok(Self {
            client,
            base_url: base_url.trim_end_matches('/').to_string(),
            username: username.to_string(),
            password: password.to_string(),
            authenticated: false,
        })
    }

    fn login(&mut self) -> Result<()> {
        let resp = self.client
            .post(format!("{}/login", self.base_url))
            .form(&[
                ("username", self.username.as_str()),
                ("password", self.password.as_str()),
                ("remember", "on"),
            ])
            .send()?;
        if resp.status().is_success() && !resp.url().path().ends_with("/login") {
            self.authenticated = true;
            Ok(())
        } else {
            bail!("Login failed")
        }
    }

    fn get(&mut self, path: &str, params: &[(&str, &str)]) -> Result<reqwest::blocking::Response> {
        if !self.authenticated {
            self.login()?;
        }
        let resp = self.client
            .get(format!("{}{}", self.base_url, path))
            .query(params)
            .send()?;
        if resp.url().path().ends_with("/login") {
            self.login()?;
            return Ok(self.client
                .get(format!("{}{}", self.base_url, path))
                .query(params)
                .send()?);
        }
        Ok(resp)
    }

    fn post(&mut self, path: &str, form: &HashMap<&str, &str>) -> Result<reqwest::blocking::Response> {
        if !self.authenticated {
            self.login()?;
        }
        let resp = self.client
            .post(format!("{}{}", self.base_url, path))
            .form(form)
            .send()?;
        if resp.url().path().ends_with("/login") {
            self.login()?;
            return Ok(self.client
                .post(format!("{}{}", self.base_url, path))
                .form(form)
                .send()?);
        }
        Ok(resp)
    }

    pub fn list_tasks(&mut self, search: &str, completed: &str) -> Result<Vec<Task>> {
        let resp = self.get("/api/search", &[
            ("q", search),
            ("priority", "all"),
            ("project", "all"),
            ("context", "all"),
            ("completed", completed),
        ])?;
        resp.error_for_status_ref()?;
        let data: SearchResponse = resp.json()?;
        Ok(data.tasks)
    }

    pub fn add_task(&mut self, description: &str, priority: &str, projects: &str, contexts: &str) -> Result<()> {
        let mut form = HashMap::new();
        form.insert("description", description);
        form.insert("priority", priority);
        form.insert("projects", projects);
        form.insert("contexts", contexts);
        self.post("/add", &form)?.error_for_status()?;
        Ok(())
    }

    pub fn toggle_complete(&mut self, id: usize) -> Result<()> {
        self.get(&format!("/complete/{id}"), &[])?.error_for_status()?;
        Ok(())
    }

    pub fn delete_task(&mut self, id: usize) -> Result<()> {
        self.get(&format!("/delete/{id}"), &[])?.error_for_status()?;
        Ok(())
    }

    pub fn edit_task(&mut self, id: usize, description: &str, priority: &str, projects: &str, contexts: &str) -> Result<()> {
        let mut form = HashMap::new();
        form.insert("description", description);
        form.insert("priority", priority);
        form.insert("projects", projects);
        form.insert("contexts", contexts);
        self.post(&format!("/edit/{id}"), &form)?.error_for_status()?;
        Ok(())
    }
}
