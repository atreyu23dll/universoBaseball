import adapter from '@sveltejs/adapter-node';

/** @type {import('@sveltejs/kit').Config} */
export default {
  kit: {
    adapter: adapter(),
    // La API se consume por fetch desde el navegador contra el backend local.
    alias: { $lib: 'src/lib' }
  }
};
