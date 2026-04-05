/**
 * 华为设备处理器
 * 支持华为 H3C/华为交换机、路由器等
 */
const { DeviceHandler } = require('./base');

class HuaweiHandler extends DeviceHandler {
  constructor() {
    super();
    this.vendor = 'huawei';
    // 华为提示符：[设备名]、[设备名-视图名]、<设备名>、<设备名-视图名>
    this.promptPatterns = [
      /^\[[\w\-\.]+(?:-[\w\-\.]+)?\]/,           // [设备名-视图]
      /^<[\w\-\.]+(?:-[\w\-\.]+)?>/,            // <设备名-视图>
      /^\[[\w\-\.]+\]$/,                         // [设备名]
      /^<[\w\-\.]+>$/,                            // <设备名>
    ];
  }

  extractPrompt(output) {
    const lines = output.split('\n');
    // 从最后几行找提示符（倒序）
    for (let i = lines.length - 1; i >= 0; i--) {
      const line = lines[i].trimRight();
      for (const pat of this.promptPatterns) {
        if (pat.test(line)) return line;
      }
    }
    return null;
  }

  isWaitingInput(output) {
    const lines = output.split('\n');
    const last = lines[lines.length - 1].trim();
    // 没有提示符，且最后一行不是空白也不是确认提示
    if (!last) return false;
    for (const pat of this.promptPatterns) {
      if (pat.test(last)) return false;
    }
    // 可能是命令正在执行还没返回
    return !this.detectConfirm(output).need;
  }

  detectConfirm(output) {
    // 华为常用确认提示
    const patterns = [
      /\[Y\/N\]/,
      /是否确认/i,
      /确认要退出/i,
      /以上信息请/i,
    ];
    for (const p of patterns) {
      if (p.test(output)) {
        const m = output.match(p);
        return { need: true, pattern: m[0] };
      }
    }
    return { need: false, pattern: null };
  }

  parse(cmd, output) {
    const clean = this.cleanOutput(cmd, output);
    // display version 解析
    if (cmd.startsWith('display version')) {
      return this._parseVersion(clean);
    }
    // display device manuinfo 解析
    if (cmd.includes('manuinfo')) {
      return this._parseManuInfo(clean);
    }
    // display interface 解析
    if (cmd.startsWith('display interface')) {
      return this._parseInterface(clean);
    }
    return { raw: clean, cmd };
  }

  _parseVersion(output) {
    const result = { type: 'version', raw: output };
    const model = output.match(/H3C[SCE]?\s*[- ]*(\S+)/i) || output.match(/Huawei\s*(\S+)/i);
    const version = output.match(/Version\s+(\S+)/i);
    const serial = output.match(/Serial\s+No\.?\s*:?\s*(\S+)/i);
    if (model) result.model = model[1];
    if (version) result.version = version[1];
    if (serial) result.serial = serial[1];
    return result;
  }

  _parseManuInfo(output) {
    const result = { type: 'manuinfo', raw: output };
    const mac = output.match(/MAC\s+Address\s*:?\s*([0-9a-fA-F:]+)/i);
    const sn = output.match(/Serial\s+Number\s*:?\s*(\S+)/i);
    if (mac) result.mac = mac[1];
    if (sn) result.sn = sn[1];
    return result;
  }

  _parseInterface(output) {
    const result = { type: 'interface', raw: output };
    const status = output.match(/Current\s+state\s*:?\s*(\S+)/i);
    const speed = output.match(/Speed\s*:?\s*(\d+)/i);
    const duplex = output.match(/Duplex\s*:?\s*(\S+)/i);
    if (status) result.status = status[1];
    if (speed) result.speed = speed[1];
    if (duplex) result.duplex = duplex[1];
    return result;
  }
}

if (typeof module !== 'undefined' && module.exports) {
  module.exports = { HuaweiHandler };
}
