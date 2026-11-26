package co.finanzassinfiltro.fsf_app

import android.content.Intent
import android.content.pm.ApplicationInfo
import android.os.Bundle
import android.provider.Settings
import android.view.WindowManager
import io.flutter.embedding.android.FlutterFragmentActivity
import io.flutter.embedding.engine.FlutterEngine
import io.flutter.plugin.common.MethodChannel

class MainActivity : FlutterFragmentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        // En release, la app no aparece en la pantalla de recientes ni en capturas (datos
        // financieros). En debug se deja desactivado para poder hacer capturas de prueba.
        val debuggable = (applicationInfo.flags and ApplicationInfo.FLAG_DEBUGGABLE) != 0
        if (!debuggable) {
            window.setFlags(WindowManager.LayoutParams.FLAG_SECURE, WindowManager.LayoutParams.FLAG_SECURE)
        }
    }

    override fun configureFlutterEngine(flutterEngine: FlutterEngine) {
        super.configureFlutterEngine(flutterEngine)
        // «Avisos» en Fuentes de Datos: si el usuario negó el permiso, Android ya no lo vuelve a
        // preguntar; se abren los ajustes de notificaciones de la app (Paso 14).
        MethodChannel(flutterEngine.dartExecutor.binaryMessenger, "fsf/avisos").setMethodCallHandler { call, result ->
            if (call.method == "abrirAjustes") {
                startActivity(
                    Intent(Settings.ACTION_APP_NOTIFICATION_SETTINGS)
                        .putExtra(Settings.EXTRA_APP_PACKAGE, packageName)
                        .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK),
                )
                result.success(null)
            } else {
                result.notImplemented()
            }
        }
    }
}
