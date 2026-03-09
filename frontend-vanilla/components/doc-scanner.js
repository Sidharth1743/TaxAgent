/**
 * Document Scanner — camera capture and file upload for tax documents.
 */

const DocScanner = (() => {
  let onImageCaptured = null;

  function init(callback) {
    onImageCaptured = callback;

    const cameraBtn = document.getElementById('cameraBtn');
    const fileInput = document.getElementById('fileInput');

    if (cameraBtn && fileInput) {
      cameraBtn.addEventListener('click', () => fileInput.click());
      fileInput.addEventListener('change', handleFileSelect);
    }
  }

  function handleFileSelect(e) {
    const file = e.target.files[0];
    if (!file) return;

    const reader = new FileReader();
    reader.onload = (ev) => {
      const base64 = ev.target.result.split(',')[1]; // strip data:...;base64, prefix
      const mimeType = file.type || 'image/jpeg';

      if (onImageCaptured) {
        onImageCaptured({
          data: base64,
          mime_type: mimeType,
          filename: file.name,
        });
      }
    };
    reader.readAsDataURL(file);

    // Reset input so same file can be selected again
    e.target.value = '';
  }

  return { init };
})();
