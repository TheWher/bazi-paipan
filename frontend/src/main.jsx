import React from 'react';
import { createRoot } from 'react-dom/client';
import { Iztrolabe } from 'react-iztro';

// 挂载函数——ziwei.html 调用 window.mountZiweiChart(containerId, props)
window.mountZiweiChart = function (containerId, props) {
  const container = document.getElementById(containerId);
  if (!container) return;
  const root = createRoot(container);
  root.render(
    React.createElement(Iztrolabe, {
      birthday: props.birthday || '1991-8-15',
      birthTime: props.birthTime ?? 1,
      birthdayType: props.birthdayType || 'solar',
      gender: props.gender || 'male',
      horoscopeDate: props.horoscopeDate || new Date(),
      horoscopeHour: props.horoscopeHour ?? 0,
    })
  );
};
