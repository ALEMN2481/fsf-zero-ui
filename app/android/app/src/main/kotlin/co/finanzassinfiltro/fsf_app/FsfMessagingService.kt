package co.finanzassinfiltro.fsf_app

import android.app.ActivityManager
import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Intent
import android.net.Uri
import android.os.Build
import android.util.Log
import com.google.firebase.messaging.RemoteMessage
import io.flutter.plugins.firebase.messaging.FlutterFirebaseMessagingService

/**
 * Avisos push (Paso 14, D16). El backend envía mensajes solo de datos y aquí se arma la
 * notificación: VISIBILITY_PRIVATE con una versión pública genérica, para que en la pantalla de
 * bloqueo solo se vea el título («Nuevo gasto registrado»), nunca el monto.
 * Con la app en primer plano no se muestra nada: la app refresca y lo dice con un aviso breve.
 */
class FsfMessagingService : FlutterFirebaseMessagingService() {
    override fun onMessageReceived(message: RemoteMessage) {
        super.onMessageReceived(message)
        val data = message.data
        val kind = data["tipo"] ?: return
        // RQN 04: de que Gmail recibió el correo a que el teléfono tiene el aviso (sin contenido).
        data["received_ms"]?.toLongOrNull()?.let {
            Log.i("fsf.push", "latencia correo→aviso ms=${System.currentTimeMillis() - it} tipo=$kind")
        }
        if (inForeground()) return
        val title = data["title"] ?: return
        val link = when (kind) {
            "reconectar_gmail" -> "co.finanzassinfiltro.fsfapp://fuentes"
            else -> "co.finanzassinfiltro.fsfapp://movimiento/${data["transaction_id"] ?: return}"
        }
        show(kind, title, data["body"].orEmpty(), data["public_title"] ?: title, link)
    }

    private fun inForeground(): Boolean {
        val info = ActivityManager.RunningAppProcessInfo()
        ActivityManager.getMyMemoryState(info)
        return info.importance == ActivityManager.RunningAppProcessInfo.IMPORTANCE_FOREGROUND
    }

    private fun show(kind: String, title: String, body: String, publicTitle: String, link: String) {
        val manager = getSystemService(NotificationManager::class.java)
        val channel = if (kind == "reconectar_gmail") CHANNEL_ACCOUNT else CHANNEL_MOVEMENTS
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            manager.createNotificationChannel(
                NotificationChannel(CHANNEL_MOVEMENTS, "Movimientos", NotificationManager.IMPORTANCE_HIGH),
            )
            manager.createNotificationChannel(
                NotificationChannel(CHANNEL_ACCOUNT, "Conexión con Gmail", NotificationManager.IMPORTANCE_DEFAULT),
            )
        }
        val open = Intent(Intent.ACTION_VIEW, Uri.parse(link)).setPackage(packageName)
            .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_SINGLE_TOP)
        val id = link.hashCode()
        val tap = PendingIntent.getActivity(
            this, id, open, PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT,
        )
        // Lo único que se ve en la pantalla de bloqueo: el título genérico, sin cifras.
        val publicVersion = builder(channel).setContentTitle(publicTitle).setContentIntent(tap).build()
        val notification = builder(channel)
            .setContentTitle(title)
            .setContentText(body)
            .setStyle(Notification.BigTextStyle().bigText(body))
            .setVisibility(Notification.VISIBILITY_PRIVATE)
            .setPublicVersion(publicVersion)
            .setContentIntent(tap)
            .setAutoCancel(true)
            .build()
        manager.notify(id, notification)
    }

    @Suppress("DEPRECATION")
    private fun builder(channel: String): Notification.Builder {
        val b = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            Notification.Builder(this, channel)
        } else {
            Notification.Builder(this)
        }
        return b.setSmallIcon(R.drawable.ic_stat_fsf).setCategory(Notification.CATEGORY_STATUS)
    }

    companion object {
        const val CHANNEL_MOVEMENTS = "movimientos"
        const val CHANNEL_ACCOUNT = "conexion"
    }
}
