/**
 * 设备处理器基类
 * 所有厂商处理器继承此类，实现厂商特定的匹配逻辑
 */
class DeviceHandler {
  constructor() {
    this.vendor = 'generic';
    this.promptPatterns = [];
    this.viewPatterns = [];
  }

  /**
   * 从输出中识别当前提示符
   * @param {string} output - 设备返回的原始输出
   * @returns {string|null} 提取到的提示符，如 '[设备名]'
   */
  extractPrompt(output) {
    for (const pat of this.promptPatterns) {
      const m = output.match(pat);
      if (m) return m[0];
    }
    return null;
  }

  /**
   * 判断输出是否还在等待输入（未出现提示符）
   * @param {string} output
   * @returns {boolean}
   */
  isWaitingInput(output) {
    // 子类可覆盖
    return false;
  }

  /**
   * 判断是否出现了需要确认的提示（如 [Y/N]）
   * @param {string} output
   * @returns {{need: boolean, pattern: string|null}}
   */
  detectConfirm(output) {
    const m = output.match(/\[Y\/N\]|\[Y\/N\]\s*$/i);
    return { need: !!m, pattern: m ? m[0] : null };
  }

  /**
   * 命令回显清理（去掉命令本身，只留输出）
   * @param {string} cmd
   * @param {string} output
   * @returns {string}
   */
  cleanOutput(cmd, output) {
    // 去掉命令回显行
    const lines = output.split('\n');
    const clean = lines.filter(l => l.trim() !== cmd.trim() && l.trim() !== '');
    return clean.join('\n').trim();
  }

  /**
   * 从输出中解析关键信息（供 AI 提取）
   * @param {string} cmd - 执行了什么命令
   * @param {string} output - 原始输出
   * @returns {object} 解析结果
   */
  parse(cmd, output) {
    return { raw: output, cmd };
  }
}

if (typeof module !== 'undefined' && module.exports) {
  module.exports = { DeviceHandler };
}
