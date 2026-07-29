package uy.kohesive.injekt

/**
 * Minimal Injekt DI shim. Real extensions only do
 *   `private val network: NetworkHelper by injectLazy()`  and occasionally
 *   `Injekt.get<Application>()`. The runner registers the singletons it needs.
 */
class InjektScope {
    val instances = HashMap<Class<*>, Any>()

    fun getByClass(cls: Class<*>): Any =
        instances[cls] ?: error("Injekt: no instance registered for $cls")

    /** Register a singleton keyed by its concrete class. */
    fun addSingleton(obj: Any): InjektScope {
        instances[obj.javaClass] = obj
        return this
    }

    /** Register a singleton under an explicit key type (for interface/abstract lookups). */
    fun addSingletonAs(key: Class<*>, obj: Any): InjektScope {
        instances[key] = obj
        return this
    }
}

var Injekt = InjektScope()

inline fun <reified T : Any> injectLazy(): Lazy<T> = lazy { Injekt.getByClass(T::class.java) as T }
inline fun <reified T : Any> injectValue(): Lazy<T> = lazy { Injekt.getByClass(T::class.java) as T }
inline fun <reified T : Any> InjektScope.injectLazy(): Lazy<T> = lazy { getByClass(T::class.java) as T }
