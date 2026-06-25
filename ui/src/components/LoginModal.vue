<script setup>
import { reactive } from "vue";
import BaseModal from "./BaseModal.vue";
import { closeLogin, loginWithPassword, useAuthStore } from "@/composables/useAuth";
import { pushToast } from "@/composables/useToast";

const auth = useAuthStore();
const form = reactive({
  username: "admin",
  password: "admin123456",
  submitting: false,
});

async function submit() {
  if (!form.username.trim() || !form.password) {
    pushToast("请输入用户名和密码", "error");
    return;
  }
  form.submitting = true;
  try {
    await loginWithPassword(form.username.trim(), form.password);
  } catch (error) {
    pushToast(error.message || "登录失败", "error");
  } finally {
    form.submitting = false;
  }
}
</script>

<template>
  <BaseModal :model-value="auth.loginOpen" title="登录系统" @update:modelValue="closeLogin">
    <div class="login-form">
      <label class="field-block">
        <span>用户名</span>
        <input v-model="form.username" type="text" autocomplete="username" />
      </label>
      <label class="field-block">
        <span>密码</span>
        <input v-model="form.password" type="password" autocomplete="current-password" />
      </label>
      <p class="node-help">默认管理员账号：admin / admin123456</p>
      <div class="modal-actions">
        <button type="button" class="ghost-btn" @click="closeLogin">取消</button>
        <button type="button" class="primary-btn" :disabled="form.submitting" @click="submit">
          {{ form.submitting ? "登录中..." : "登录" }}
        </button>
      </div>
    </div>
  </BaseModal>
</template>
