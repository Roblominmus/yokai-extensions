/*
 * Minimal stand-in for android.content.* types that leak into the extensions-lib
 * API surface. Not needed for parsing; exists only so real sources compile.
 */
package android.content

interface SharedPreferences {
    fun getString(key: String, defValue: String?): String?
    fun getBoolean(key: String, defValue: Boolean): Boolean
    fun getInt(key: String, defValue: Int): Int
    fun getLong(key: String, defValue: Long): Long
    fun getStringSet(key: String, defValue: Set<String>?): Set<String>?
    fun edit(): Editor
    interface Editor {
        fun putString(key: String, value: String?): Editor
        fun putBoolean(key: String, value: Boolean): Editor
        fun apply()
    }
}

open class Context
