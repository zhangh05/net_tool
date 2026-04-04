// Minimal Projects Vue App - Login Removed
(function() {
  // Auto-login as admin
  var session = { username: 'admin', token: 'token_' + Math.random().toString(36).substring(2, 10), project_id: null };
  localStorage.setItem('netops_session', JSON.stringify(session));

  // Wait for DOM
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }

  function init() {
    var App = {
      data: function() {
        return {
          projects: [],
          showForm: false,
          newName: '',
          deleteId: null,
          loading: false,
          error: '',
          username: 'admin'
        };
      },
      mounted: function() {
        this.fetchProjects();
      },
      methods: {
        fetchProjects: function() {
          var self = this;
          this.loading = true;
          fetch('/api/projects/')
            .then(function(r) { return r.json(); })
            .then(function(data) {
              self.projects = data.projects || [];
              self.loading = false;
            })
            .catch(function(e) {
              self.error = '加载失败: ' + e.message;
              self.loading = false;
            });
        },
        createProject: function() {
          var self = this;
          if (!this.newName.trim()) return;
          fetch('/api/projects/', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({name: this.newName.trim()})
          })
            .then(function(r) { return r.json(); })
            .then(function(d) {
              if (d.id) {
                self.projects.unshift(d);
                self.newName = '';
                self.showForm = false;
              } else {
                self.error = d.error || '创建失败';
              }
            })
            .catch(function(e) {
              self.error = '创建失败: ' + e.message;
            });
        },
        deleteProject: function(id) {
          var self = this;
          fetch('/api/projects/' + id, {method: 'DELETE'})
            .then(function(r) { return r.json(); })
            .then(function(d) {
              if (d.ok || d.deleted) {
                self.projects = self.projects.filter(function(p) { return p.id !== id; });
                self.deleteId = null;
              } else {
                self.error = d.error || '删除失败';
              }
            })
            .catch(function(e) {
              self.error = '删除失败: ' + e.message;
            });
        },
        openProject: function(id) {
          window.location.href = '/?project_id=' + id;
        },
        formatDate: function(d) {
          if (!d) return '';
          return new Date(d).toLocaleString('zh-CN');
        }
      },
      template: '' +
        '<div style="min-height:100vh;background:#f8fafc;font-family:system-ui,sans-serif;">' +
          '<div style="max-width:900px;margin:0 auto;padding:40px 20px;">' +
            '<div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:32px;">' +
              '<div>' +
                '<h1 style="margin:0;font-size:24px;font-weight:700;color:#1a1a2e;">🛠️ NetTool 运维平台</h1>' +
                '<p style="margin:8px 0 0;color:#64748b;font-size:14px;">欢迎，{{ username }}</p>' +
              '</div>' +
              '<button @click="showForm=true" style="background:#3b82f6;color:#fff;border:none;border-radius:8px;padding:10px 20px;font-size:14px;font-weight:600;cursor:pointer;">+ 新建项目</button>' +
            '</div>' +
            '<div v-if="error" style="background:#fef2f2;color:#ef4444;padding:12px 16px;border-radius:8px;margin-bottom:20px;font-size:14px;">{{ error }}</div>' +
            '<div v-if="loading" style="text-align:center;color:#64748b;padding:40px;">加载中...</div>' +
            '<div v-else-if="projects.length === 0" style="text-align:center;color:#64748b;padding:60px 20px;background:#fff;border-radius:12px;border:1px solid #e2e8f0;">' +
              '<p style="font-size:16px;margin:0 0 12px;">暂无项目</p>' +
              '<button @click="showForm=true" style="background:#3b82f6;color:#fff;border:none;border-radius:8px;padding:10px 20px;font-size:14px;cursor:pointer;">创建第一个项目</button>' +
            '</div>' +
            '<div v-else style="display:grid;grid-template-columns:repeat(auto-fill,minmax(280px,1fr));gap:16px;">' +
              '<div v-for="p in projects" :key="p.id" @click="openProject(p.id)" ' +
                'style="background:#fff;border:1px solid #e2e8f0;border-radius:12px;padding:20px;cursor:pointer;transition:all 0.15s;hover:box-shadow:0 4px 12px rgba(0,0,0,0.1);">' +
                '<div style="display:flex;justify-content:space-between;align-items:start;margin-bottom:12px;">' +
                  '<h3 style="margin:0;font-size:16px;font-weight:600;color:#1a1a2e;">{{ p.name }}</h3>' +
                  '<button @click.stop="deleteId=p.id" style="background:none;border:none;color:#94a3b8;font-size:18px;cursor:pointer;padding:4px;">&times;</button>' +
                '</div>' +
                '<p style="margin:0;font-size:12px;color:#94a3b8;">{{ formatDate(p.updated) }}</p>' +
              '</div>' +
            '</div>' +
          '</div>' +
          '<div v-if="showForm" style="position:fixed;top:0;left:0;width:100%;height:100%;background:rgba(0,0,0,0.5);display:flex;align-items:center;justify-content:center;z-index:1000;">' +
            '<div style="background:#fff;border-radius:12px;padding:32px;width:400px;max-width:90vw;">' +
              '<h3 style="margin:0 0 20px;font-size:18px;font-weight:600;">新建项目</h3>' +
              '<input v-model="newName" @keyup.enter="createProject" placeholder="项目名称" ' +
                'style="width:100%;padding:10px 14px;border:1px solid #e2e8f0;border-radius:8px;font-size:14px;box-sizing:border-box;outline:none;">' +
              '<div style="display:flex;gap:12px;margin-top:20px;justify-content:flex-end;">' +
                '<button @click="showForm=false;newName=\'\'" style="background:#f1f5f9;border:none;color:#64748b;padding:10px 20px;border-radius:8px;font-size:14px;cursor:pointer;">取消</button>' +
                '<button @click="createProject" style="background:#3b82f6;color:#fff;border:none;padding:10px 20px;border-radius:8px;font-size:14px;font-weight:600;cursor:pointer;">创建</button>' +
              '</div>' +
            '</div>' +
          '</div>' +
          '<div v-if="deleteId" style="position:fixed;top:0;left:0;width:100%;height:100%;background:rgba(0,0,0,0.5);display:flex;align-items:center;justify-content:center;z-index:1000;">' +
            '<div style="background:#fff;border-radius:12px;padding:32px;width:360px;max-width:90vw;text-align:center;">' +
              '<p style="margin:0 0 20px;font-size:15px;color:#374151;">确定要删除这个项目吗？此操作不可恢复。</p>' +
              '<div style="display:flex;gap:12px;justify-content:center;">' +
                '<button @click="deleteId=null" style="background:#f1f5f9;border:none;color:#64748b;padding:10px 24px;border-radius:8px;font-size:14px;cursor:pointer;">取消</button>' +
                '<button @click="deleteProject(deleteId)" style="background:#ef4444;color:#fff;border:none;padding:10px 24px;border-radius:8px;font-size:14px;font-weight:600;cursor:pointer;">删除</button>' +
              '</div>' +
            '</div>' +
          '</div>' +
        '</div>'
    };

    new Vue({ render: function(h) { return h(App); } }).$mount('#app');
  }
})();
