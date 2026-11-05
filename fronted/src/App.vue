<script setup lang="ts">
import { onLaunch } from "@dcloudio/uni-app";

onLaunch(() => {
  console.log("ClassMate 学生端启动");
});
</script>

<style>
page {
  background: #f4efe4;
  color: #16233a;
  font-family: "PingFang SC", "Microsoft YaHei", "Noto Sans SC", sans-serif;
}

.page {
  min-height: 100vh;
  padding: 28rpx 28rpx 60rpx;
  box-sizing: border-box;
}

.card {
  background: #ffffff;
  border-radius: 26rpx;
  padding: 30rpx;
  margin-bottom: 24rpx;
  box-shadow: 0 12rpx 30rpx rgba(22, 35, 58, 0.06);
}

.card-title {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 18rpx;
}

.card-title text:first-child {
  font-size: 30rpx;
  font-weight: 700;
}

.muted {
  font-size: 22rpx;
  color: #8792a5;
}

.label {
  font-size: 22rpx;
  color: #8792a5;
  margin-bottom: 8rpx;
  display: block;
}

.input {
  width: 100%;
  box-sizing: border-box;
  background: #fbf8f1;
  border: 2rpx solid rgba(22, 35, 58, 0.12);
  border-radius: 18rpx;
  padding: 20rpx 22rpx;
  font-size: 28rpx;
  color: #16233a;
}

.textarea {
  width: 100%;
  box-sizing: border-box;
  background: #fbf8f1;
  border: 2rpx solid rgba(22, 35, 58, 0.12);
  border-radius: 18rpx;
  padding: 20rpx 22rpx;
  font-size: 28rpx;
  min-height: 160rpx;
}

.btn {
  background: #ffffff;
  border: 2rpx solid rgba(22, 35, 58, 0.18);
  border-radius: 18rpx;
  padding: 20rpx 28rpx;
  font-size: 28rpx;
  font-weight: 600;
  color: #16233a;
  text-align: center;
}

.btn.primary {
  background: #16233a;
  border-color: #16233a;
  color: #ffffff;
}

.btn.blue {
  background: #1f5fb4;
  border-color: #1f5fb4;
  color: #ffffff;
}

.btn.ghost {
  background: transparent;
  border-color: transparent;
  color: #4c5a72;
}

.btn.disabled {
  opacity: 0.5;
}

.row {
  display: flex;
  align-items: center;
  gap: 16rpx;
  flex-wrap: wrap;
}

.tag {
  display: inline-block;
  font-size: 20rpx;
  padding: 4rpx 14rpx;
  border-radius: 999rpx;
  background: #e6eefb;
  color: #1f5fb4;
  margin-right: 8rpx;
}

.tag.green {
  background: #e0f5ee;
  color: #0e8a6a;
}

.tag.amber {
  background: #fdf0d4;
  color: #b7791f;
}

.tag.red {
  background: #fbe7e4;
  color: #c2453a;
}

.tag.grey {
  background: #eef1f5;
  color: #4c5a72;
}

.error {
  background: #fbe7e4;
  color: #c2453a;
  padding: 16rpx 20rpx;
  border-radius: 16rpx;
  font-size: 24rpx;
  margin-top: 16rpx;
}

.notice {
  background: #fdf0d4;
  color: #8a5b13;
  padding: 16rpx 20rpx;
  border-radius: 16rpx;
  font-size: 24rpx;
  line-height: 1.7;
  margin-top: 16rpx;
}

.bar {
  height: 14rpx;
  background: #eef1f5;
  border-radius: 999rpx;
  overflow: hidden;
  flex: 1;
  margin: 0 16rpx;
}

.bar-fill {
  height: 100%;
  border-radius: 999rpx;
  background: linear-gradient(90deg, #5b9bef, #1f5fb4);
}

.bar-fill.warn {
  background: linear-gradient(90deg, #f3b96a, #d68a1f);
}

.bar-fill.bad {
  background: linear-gradient(90deg, #f29b92, #c2453a);
}

.hero {
  background: linear-gradient(150deg, #16233a, #23466f);
  color: #ffffff;
  border-radius: 30rpx;
  padding: 40rpx 34rpx;
  margin-bottom: 26rpx;
}

.hero-title {
  font-size: 40rpx;
  font-weight: 800;
  line-height: 1.35;
  display: block;
}

.hero-title .hl {
  color: #ffe66b;
}

.hero-sub {
  display: block;
  margin-top: 14rpx;
  font-size: 24rpx;
  color: rgba(255, 255, 255, 0.72);
  line-height: 1.7;
}

.code-big {
  font-size: 56rpx;
  font-weight: 800;
  letter-spacing: 8rpx;
  background: #ffe66b;
  color: #16233a;
  border-radius: 20rpx;
  padding: 12rpx 24rpx;
  display: inline-block;
}

.script-block {
  background: #fbf8f1;
  border-left: 8rpx solid #ffe66b;
  border-radius: 0 18rpx 18rpx 0;
  padding: 20rpx 24rpx;
  margin-top: 18rpx;
}

.script-label {
  font-size: 20rpx;
  letter-spacing: 2rpx;
  color: #1f5fb4;
  font-weight: 600;
  display: block;
  margin-bottom: 6rpx;
}

.script-text {
  font-size: 26rpx;
  line-height: 1.75;
  color: #4c5a72;
  display: block;
}

.seg {
  display: flex;
  background: #eef1f5;
  border-radius: 18rpx;
  padding: 6rpx;
  margin-bottom: 24rpx;
}

.seg-item {
  flex: 1;
  text-align: center;
  padding: 16rpx 0;
  font-size: 26rpx;
  color: #4c5a72;
  border-radius: 14rpx;
}

.seg-item.active {
  background: #ffffff;
  color: #16233a;
  font-weight: 700;
}

.option {
  border: 2rpx solid rgba(22, 35, 58, 0.12);
  border-radius: 18rpx;
  padding: 20rpx 22rpx;
  margin-top: 14rpx;
  font-size: 27rpx;
  color: #4c5a72;
  line-height: 1.6;
  background: #ffffff;
}

.option.active {
  border-color: #1f5fb4;
  background: #e6eefb;
  color: #16233a;
  font-weight: 600;
}

.empty {
  text-align: center;
  color: #8792a5;
  font-size: 24rpx;
  padding: 40rpx 0;
}
</style>
